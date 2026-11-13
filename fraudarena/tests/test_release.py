"""Owner: M4. Release state machine, versions, rollback, regression store (24h plan section 12)."""
from __future__ import annotations

import pytest

from fa.contracts import Cond, Event, Plan, Rule, Step
from fa.release import approve as approve_mod
from fa.release import rollback as rollback_mod
from fa.release import versions
from fa.release.versions import ReleaseError, VersionStore
from fa.verify.regression import RegressionStore

NOON = 12 * 3600


def mk_rule(rid, *conds, action="hold"):
    return Rule(id=rid, action=action, when=[Cond(f=f, op=op, v=v) for f, op, v in conds])


GOOD = mk_rule("R-night", ("night_flag", "==", 1))
BAD = mk_rule("R-never", ("n_pay_1h", ">=", 999))


def attack(pid, start=0):
    return Plan(plan_id=pid, playbook="P1", seed=1, steps=[
        Step(t=start, actor="victim", act="login", device="new"),
        Step(t=start + 180, actor="victim", act="add_payee", payee="mule"),
        Step(t=start + 480, actor="victim", act="pay", payee="mule", amount=100),
        Step(t=start + 1080, actor="victim", act="pay", payee="mule", amount=4_800_000),
        Step(t=start + 2400, actor="mule", act="cashout", amount=4_800_000),
    ])


def noon_payment(i):
    return Event(event_id=f"n{i}", ts=NOON + i * 5, type="payment", account=f"acc{i}", payee="shop",
                 amount=1000, device="d1")


@pytest.fixture
def store(tmp_path):
    return VersionStore(tmp_path / "store")


@pytest.fixture
def ctx():
    return {
        "plan": attack("pl-fail"),
        "regression_plans": [attack("pl-old")],
        "variants": [attack(f"pl-v{i}", start=i * 600) for i in range(10)],
        "normal_events": [noon_payment(i) for i in range(2000)],
        "golden_cases": [[noon_payment(i)] for i in range(3)],
    }


class FakeLedger:
    def __init__(self):
        self.records = []

    def __call__(self, action, payload):
        self.records.append((action, payload))
        return len(self.records)


# ---------------------------------------------------------------- versions

def test_fresh_store_has_baseline_v1_active(store):
    assert store.list_versions() == ["v1"] and store.active_version() == "v1"
    assert len(store.get("v1").rules) == 6


def test_versions_are_never_edited_in_place(store):
    v2 = store.get("v1").model_copy(update={"version": "v2"})
    store.save(v2, parent="v1", source="test")
    with pytest.raises(ReleaseError):
        store.save(v2, parent="v1", source="test")
    with pytest.raises(ReleaseError):
        store.save(store.get("v1"), parent=None, source="test")


def test_cannot_activate_unknown_version(store):
    with pytest.raises(ReleaseError):
        store.set_active("v9")
    with pytest.raises(KeyError):
        store.get("v9")


def test_loader_active_and_load_use_the_store(store):
    from fa.rules import loader

    assert loader.active(store).version == "v1" and loader.load("v1", store).version == "v1"


# ---------------------------------------------------------------- propose / verify

def test_good_patch_reaches_awaiting_approval_with_gates_and_shadow(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    p = store.get_patch(pid)
    assert p["state"] == versions.AWAITING_APPROVAL
    assert [g["gate"] for g in p["gates"]] == ["G1", "G2", "G3", "G4", "G5", "G6"]
    assert all(g["passed"] for g in p["gates"])
    assert p["shadow"]["normal"]["n"] == 2000 and p["shadow"]["regression"]["checked"] == 1


def test_bad_patch_is_rejected_with_reasons(store, ctx):
    pid = versions.propose(BAD, "defender-agent", starter="alice", ctx=ctx, store=store)
    p = store.get_patch(pid)
    assert p["state"] == versions.REJECTED and "G2" in p["reason"]
    with pytest.raises(ReleaseError):
        approve_mod.approve(pid, "bob", store=store, ledger=FakeLedger())


def test_propose_without_ctx_stays_proposed_and_cannot_be_approved(store):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", store=store)
    assert store.get_patch(pid)["state"] == versions.PROPOSED
    with pytest.raises(ReleaseError):
        approve_mod.approve(pid, "bob", store=store, ledger=FakeLedger())


def test_patch_ids_increment(store):
    assert [versions.propose(GOOD, "m", store=store) for _ in range(3)] == ["pt-1", "pt-2", "pt-3"]


# ---------------------------------------------------------------- approve / reject

def test_maker_checker_blocks_same_person(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="Alice", ctx=ctx, store=store)
    led = FakeLedger()
    with pytest.raises(ReleaseError):
        approve_mod.approve(pid, "  alice ", store=store, ledger=led)       # round starter, case/space-insensitive
    with pytest.raises(ReleaseError):
        approve_mod.approve(pid, "defender-agent", store=store, ledger=led)  # the maker
    with pytest.raises(ReleaseError):
        approve_mod.approve(pid, "", store=store, ledger=led)
    assert led.records == [] and store.active_version() == "v1"


def test_approve_promotes_new_version_and_writes_ledger(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    led = FakeLedger()
    patch = approve_mod.approve(pid, "bob", store=store, ledger=led)

    assert patch["state"] == versions.ACTIVE and patch["checker"] == "bob" and patch["new_version"] == "v2"
    assert store.active_version() == "v2"
    v2 = store.get("v2")
    assert [r.id for r in v2.rules] == ["R1", "R2", "R3", "R4", "R5", "R6", "R-night"]
    assert v2.rules[-1].added_in == "v2"
    assert len(store.get("v1").rules) == 6                                   # v1 untouched
    (action, payload), = led.records
    assert action == "promote" and payload["from"] == "v1" and payload["to"] == "v2"
    assert payload["checker"] == "bob" and payload["gates"]["G2"] == "pass"
    assert patch["ledger_seq"] == 1


def test_cannot_approve_twice(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    approve_mod.approve(pid, "bob", store=store, ledger=FakeLedger())
    with pytest.raises(ReleaseError):
        approve_mod.approve(pid, "carol", store=store, ledger=FakeLedger())


def test_ledger_failure_changes_nothing(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)

    def boom(action, payload):
        raise RuntimeError("ledger down")

    with pytest.raises(RuntimeError):
        approve_mod.approve(pid, "bob", store=store, ledger=boom)
    assert store.active_version() == "v1" and store.list_versions() == ["v1"]
    assert store.get_patch(pid)["state"] == versions.AWAITING_APPROVAL


def test_reject_by_checker(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    led = FakeLedger()
    patch = approve_mod.reject(pid, "bob", "too risky", store=store, ledger=led)
    assert patch["state"] == versions.REJECTED and patch["reason"] == "too risky"
    assert led.records[0][0] == "reject" and store.active_version() == "v1"


def test_stale_patch_cannot_be_approved_after_another_was(store, ctx):
    p1 = versions.propose(GOOD, "m", starter="alice", ctx=ctx, store=store)
    p2 = versions.propose(mk_rule("R-night2", ("night_flag", "==", 1), ("sum_1h", ">=", 0)), "m",
                          starter="alice", ctx=ctx, store=store)
    approve_mod.approve(p1, "bob", store=store, ledger=FakeLedger())
    with pytest.raises(ReleaseError):
        approve_mod.approve(p2, "bob", store=store, ledger=FakeLedger())


def test_default_ledger_skips_until_m2_lands():
    """M2's ledger is a stub that raises NotImplementedError: approve must still work."""
    from fa.ledger import chain

    try:
        chain.append("x", {})
    except NotImplementedError:
        assert approve_mod.default_ledger("x", {}) is None


# ---------------------------------------------------------------- rollback

def test_rollback_moves_pointer_and_keeps_versions(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    approve_mod.approve(pid, "bob", store=store, ledger=FakeLedger())
    led = FakeLedger()
    out = rollback_mod.rollback("v1", "bob", store=store, ledger=led)
    assert store.active_version() == "v1" and out == {"from": "v2", "to": "v1", "who": "bob", "ledger_seq": 1}
    assert store.list_versions() == ["v1", "v2"]                               # v2 kept
    assert led.records[0][0] == "rollback"


def test_rollback_validation(store):
    led = FakeLedger()
    with pytest.raises(ReleaseError):
        rollback_mod.rollback("v1", "bob", store=store, ledger=led)           # already active
    with pytest.raises(ReleaseError):
        rollback_mod.rollback("v7", "bob", store=store, ledger=led)           # unknown
    with pytest.raises(ReleaseError):
        rollback_mod.rollback("v1", " ", store=store, ledger=led)             # no name
    assert led.records == []


# ---------------------------------------------------------------- regression store

def test_regression_store_persists_and_dedupes(tmp_path):
    path = tmp_path / "reg.json"
    s = RegressionStore(path)
    assert s.add(attack("a")) and not s.add(attack("a")) and s.add(attack("b"))
    again = RegressionStore(path)                                              # new object, same file
    assert [p.plan_id for p in again.all()] == ["a", "b"]
    again.clear()
    assert RegressionStore(path).all() == []


# ---------------------------------------------------------------- API routes

def test_release_routes_map_errors_to_http(store, ctx, monkeypatch):
    from fastapi.testclient import TestClient
    from fastapi import FastAPI

    from api import routes_release

    monkeypatch.setattr(versions, "_default", store)
    monkeypatch.setattr(approve_mod, "default_ledger", FakeLedger())
    app = FastAPI()
    app.include_router(routes_release.router)
    client = TestClient(app)

    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    assert client.get("/api/patches").json()[0]["id"] == pid
    assert client.post(f"/api/patches/{pid}/approve", params={"checker": "alice"}).status_code == 409
    assert client.post("/api/patches/pt-99/approve", params={"checker": "bob"}).status_code == 404
    ok = client.post(f"/api/patches/{pid}/approve", params={"checker": "bob"})
    assert ok.status_code == 200 and ok.json()["new_version"] == "v2"
    assert client.post("/api/rollback", params={"to_version": "v1", "checker": "bob"}).json()["to"] == "v1"
    assert client.post("/api/rollback", params={"to_version": "v1", "checker": "bob"}).status_code == 409


# ---------------------------------------------------------------- M4-16: offline path, determinism, edges

def test_verifier_and_release_never_import_agents():
    """Gates are plain code: they must work with the LLM off, so no module under
    fa.verify / fa.release / fa.core.engine may import fa.agents (24h plan section 11)."""
    import subprocess
    import sys

    code = ("import sys; import fa.verify.gates, fa.verify.shadow, fa.release.versions, fa.release.approve, "
            "fa.release.rollback, fa.core.engine, api.routes_release; "
            "bad=[m for m in sys.modules if m.startswith('fa.agents') or m in ('anthropic','openai','optuna')]; "
            "print(bad); sys.exit(1 if bad else 0)")
    r = subprocess.run([sys.executable, "-c", code], capture_output=True, text=True)
    assert r.returncode == 0, r.stdout + r.stderr


def test_gate_results_are_deterministic(ctx):
    from fa.verify import gates

    from fa.rules.loader import load_baseline
    from fa.contracts import RuleSet

    cand = RuleSet(version="v2", rules=[*load_baseline().rules, GOOD])
    ctx = {**ctx, "base_rule_set": load_baseline()}
    run = lambda: [(r.gate, r.passed, r.reason, r.evidence) for r in gates.run_gates(cand, ctx)]  # noqa: E731
    assert run() == run()


def test_cannot_reject_after_approval_or_twice(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    approve_mod.reject(pid, "bob", "no", store=store, ledger=FakeLedger())
    with pytest.raises(ReleaseError):
        approve_mod.reject(pid, "carol", "again", store=store, ledger=FakeLedger())
    with pytest.raises(ReleaseError):
        approve_mod.approve(pid, "carol", store=store, ledger=FakeLedger())


def test_reject_requires_a_named_checker_who_is_not_the_maker(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    with pytest.raises(ReleaseError):
        approve_mod.reject(pid, "", "x", store=store, ledger=FakeLedger())
    assert store.get_patch(pid)["state"] == versions.AWAITING_APPROVAL


def test_rollback_ledger_failure_keeps_pointer(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    approve_mod.approve(pid, "bob", store=store, ledger=FakeLedger())

    def boom(action, payload):
        raise RuntimeError("ledger down")

    with pytest.raises(RuntimeError):
        rollback_mod.rollback("v1", "bob", store=store, ledger=boom)
    assert store.active_version() == "v2"                       # ledger first, pointer second


def test_promote_after_rollback_builds_on_the_restored_version(store, ctx):
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=store)
    approve_mod.approve(pid, "bob", store=store, ledger=FakeLedger())
    rollback_mod.rollback("v1", "bob", store=store, ledger=FakeLedger())
    p2 = versions.propose(mk_rule("R-night3", ("night_flag", "==", 1), ("sum_1h", ">=", 0)), "m",
                          starter="alice", ctx=ctx, store=store)
    patch = approve_mod.approve(p2, "bob", store=store, ledger=FakeLedger())
    assert patch["parent_version"] == "v1" and patch["new_version"] == "v3"   # v2 is kept, never reused
    assert store.list_versions() == ["v1", "v2", "v3"]


def test_state_files_survive_a_new_store_object(tmp_path, ctx):
    a = VersionStore(tmp_path / "s")
    pid = versions.propose(GOOD, "defender-agent", starter="alice", ctx=ctx, store=a)
    approve_mod.approve(pid, "bob", store=a, ledger=FakeLedger())
    b = VersionStore(tmp_path / "s")                              # simulates a restart
    assert b.active_version() == "v2" and b.get_patch(pid)["state"] == versions.ACTIVE
