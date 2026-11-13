"""Owner: M4. Fault tests for the demo (24h plan section 12, M4-19): the pipeline must behave when
the network does not.

  1. LLM off, warm cache: a full round (attack -> defend -> gates) still produces a patch.
  2. Cache miss with no network and no key: a clear error, nothing half-promoted.
  3. Reset between runs: v1 active, patches and regression plans cleared, ledger kept and appended to.

Every test runs against temporary stores; none touches data/ or the real ledger.
"""
from __future__ import annotations

import warnings

import pytest

from fa import orchestrator
from fa.agents import llm
from fa.config import load_config
from fa.release import versions
from fa.release.versions import VersionStore
from fa.verify import regression
from fa.verify.regression import RegressionStore

warnings.filterwarnings("ignore")


def _cfg(tmp_path, key):
    base = load_config()
    params = {**base.params,
              "agents": {**base.section("agents"), "cache_dir": str(tmp_path / "llm_cache")},
              "search": {**base.section("search"), "trials": 12}}
    return base.model_copy(update={"llm_api_key": key, "params": params})


@pytest.fixture
def lab(tmp_path, monkeypatch):
    """Temp rule store + regression store + LLM cache; no real network call is possible."""
    store = VersionStore(tmp_path / "rules")
    monkeypatch.setattr(versions, "_default", store)
    monkeypatch.setattr(regression, "_default", RegressionStore(tmp_path / "reg.json"))
    monkeypatch.delenv("LLM_OFFLINE_FALLBACK", raising=False)

    def network(*a, **k):
        raise AssertionError("network call attempted")

    monkeypatch.setattr(llm.httpx, "post", network)

    def use(key):
        cfg = _cfg(tmp_path, key)
        monkeypatch.setattr(llm, "load_config", lambda *a, **k: cfg)
        monkeypatch.setattr(orchestrator, "load_config", lambda *a, **k: cfg)

    use(None)
    return type("Lab", (), {"store": store, "use": staticmethod(use), "calls": []})


def _fake_llm(lab, monkeypatch):
    """Stands in for the provider and counts calls; answers from the schema, like the offline stub."""
    def fake(prompt, schema, model, key):
        lab.calls.append(prompt[:40])
        return llm._offline_answer(schema, "fake")

    monkeypatch.setattr(llm, "_call_groq", fake)


def test_warm_cache_runs_a_full_round_with_the_llm_off(lab, monkeypatch):
    # Warm: a key is set, the (fake) provider answers, answers are cached on disk.
    lab.use("gsk_test")
    _fake_llm(lab, monkeypatch)
    orchestrator.run_round("P1", "alice")
    warm_calls = len(lab.calls)
    patches = lab.store.list_patches()
    assert warm_calls >= 2 and len(patches) == 1                      # attacker + defender asked once each
    assert patches[0]["state"] == versions.AWAITING_APPROVAL

    # Cold again: no key, network blocked by the fixture. Same seed -> same prompts -> all cache hits.
    lab.use(None)
    orchestrator.run_round("P1", "alice")
    assert len(lab.calls) == warm_calls                               # the provider was never called again
    again = lab.store.list_patches()
    assert len(again) == 2 and again[1]["state"] == versions.AWAITING_APPROVAL
    assert again[1]["rule"]["when"] == again[0]["rule"]["when"]       # deterministic: same fix both times
    assert lab.store.active_version() == "v1"                         # nothing promoted by running a round


def test_cache_miss_without_network_is_a_clear_error_and_changes_nothing(lab):
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        orchestrator.run_round("P1", "alice")
    assert lab.store.list_patches() == []
    assert lab.store.active_version() == "v1" and lab.store.list_versions() == ["v1"]


def test_api_reports_the_failure_instead_of_crashing(lab, monkeypatch):
    from api import routes_rounds

    saved = []
    monkeypatch.setattr(routes_rounds, "save_round", lambda rid, pb, who, state: saved.append(state))
    routes_rounds._background_round("rnd-x", "P1", "alice")           # the thread body: must not raise
    assert saved[0] == "RUNNING" and saved[-1].startswith("ERROR") and "LLM_API_KEY" in saved[-1]


def test_gates_and_release_need_no_llm_at_all(lab):
    """Verify -> approve -> rollback with no key, an empty cache and the network blocked."""
    from fa.release import approve, rollback
    from tests.test_release import GOOD, attack, noon_payment

    ctx = {"plan": attack("pl-fail"), "regression_plans": [attack("pl-old")],
           "variants": [attack(f"pl-v{i}", start=i * 600) for i in range(10)],
           "normal_events": [noon_payment(i) for i in range(2000)],
           "golden_cases": [[noon_payment(i)] for i in range(3)]}
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=lab.store)
    assert lab.store.get_patch(pid)["state"] == versions.AWAITING_APPROVAL
    approve.approve(pid, "bob", store=lab.store, ledger=lambda a, d: 1)
    assert lab.store.active_version() == "v2"
    rollback.rollback("v1", "bob", store=lab.store, ledger=lambda a, d: 2)
    assert lab.store.active_version() == "v1"


# ------------------------------------------------------------------ reset between runs

def test_world_reset_returns_to_a_clean_v1(lab, monkeypatch, tmp_path):
    from fa.contracts import Cond, Plan, Rule, Step
    from fa.release import approve
    from api import routes_core, routes_rounds

    rule = Rule(id="R7", action="hold", when=[Cond(f="night_flag", op="==", v=1)])
    pid = versions.propose(rule, "m", starter="alice", store=lab.store)
    p = lab.store.get_patch(pid)
    p.update(state=versions.AWAITING_APPROVAL, gates=[])
    lab.store.save_patch(p)
    approve.approve(pid, "bob", store=lab.store, ledger=lambda a, d: 1)
    regression.add(Plan(plan_id="pl-1", playbook="P1", seed=1, steps=[Step(t=0, actor="victim", act="login")]))
    routes_core._sim_state.accounts["leftover"] = object()
    assert lab.store.active_version() == "v2" and regression.all()

    appended = []
    monkeypatch.setattr("api.db.reset_run_data", lambda: {"rounds": 3})
    monkeypatch.setattr("fa.ledger.chain.append", lambda action, payload: appended.append((action, payload))
                        or type("R", (), {"seq": 9})())

    for _ in range(2):                                                # twice: reset is idempotent
        out = routes_rounds.reset_world()
        assert out["active_version"] == "v1" and out["ledger_seq"] == 9

    assert lab.store.active_version() == "v1" and lab.store.list_versions() == ["v1"]
    assert lab.store.list_patches() == []
    assert regression.all() == []
    assert "leftover" not in routes_core._sim_state.accounts
    assert [a for a, _ in appended] == ["world_reset", "world_reset"]  # the ledger is appended to, never cleared
    assert lab.store.new_patch_id() == "pt-1"                         # numbering restarts for the next demo
