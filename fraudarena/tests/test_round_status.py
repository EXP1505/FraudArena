"""Owner: M4. A round must stop saying "awaiting approval" once its patch has been decided."""
from __future__ import annotations

import pytest

from api import routes_rounds
from api.db import init_db, save_round
from fa.release import approve, versions
from fa.release.versions import VersionStore
from tests.test_release import GOOD, attack, noon_payment


@pytest.fixture
def ctx():
    return {"plan": attack("pl-fail"), "regression_plans": [attack("pl-old")],
            "variants": [attack(f"pl-v{i}", start=i * 600) for i in range(10)],
            "normal_events": [noon_payment(i) for i in range(2000)],
            "golden_cases": [[noon_payment(i)] for i in range(3)]}


@pytest.fixture
def lab(tmp_path, monkeypatch):
    init_db()
    store = VersionStore(tmp_path / "rules")
    monkeypatch.setattr(versions, "_default", store)
    return store


def _round(rid):
    save_round(rid, "P1", "alice", "AWAITING_APPROVAL")


def test_propose_records_the_round_that_produced_it(lab, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=lab, round_id="rnd-a")
    assert lab.get_patch(pid)["round_id"] == "rnd-a"
    assert lab.get_patch(versions.propose(GOOD, "m", store=lab))["round_id"] is None      # optional


def test_round_stays_awaiting_until_its_patch_is_decided(lab, ctx):
    _round("rnd-wait")
    versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=lab, round_id="rnd-wait")
    assert routes_rounds.get_round("rnd-wait")["state"] == "AWAITING_APPROVAL"
    assert routes_rounds.get_round("rnd-wait")["patch_id"] == "pt-1"


def test_round_becomes_approved_when_the_patch_goes_live(lab, ctx):
    _round("rnd-ok")
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=lab, round_id="rnd-ok")
    approve.approve(pid, "bob", store=lab, ledger=lambda a, d: 1)
    assert routes_rounds.get_round("rnd-ok")["state"] == "APPROVED"
    assert {r["id"]: r["state"] for r in routes_rounds.list_rounds()}["rnd-ok"] == "APPROVED"


def test_round_becomes_rejected_when_the_patch_is_rejected(lab, ctx):
    _round("rnd-no")
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=lab, round_id="rnd-no")
    approve.reject(pid, "bob", "too risky", store=lab, ledger=lambda a, d: 1)
    assert routes_rounds.get_round("rnd-no")["state"] == "REJECTED"


def test_a_different_rounds_patch_does_not_change_this_round(lab, ctx):
    _round("rnd-other")
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=lab, round_id="rnd-elsewhere")
    approve.approve(pid, "bob", store=lab, ledger=lambda a, d: 1)
    assert routes_rounds.get_round("rnd-other")["state"] == "AWAITING_APPROVAL"


def test_the_orchestrator_hands_its_round_id_to_propose(monkeypatch, lab):
    """run_round_detailed(round_id=...) must pass that id on, or the link above never exists."""
    import inspect

    from fa import orchestrator

    assert "round_id=round_id" in inspect.getsource(orchestrator.run_round_detailed)
