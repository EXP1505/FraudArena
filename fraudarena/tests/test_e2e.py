"""Owner: M1. A full P1 round with the LLM cache warm ends ACTIVE with a
ledger that verifies (CP4 / make demo smoke test).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from fa.agents.attacker import _param_schema, _prompt
from fa.agents.cache import cache_key, put
from fa.config import load_config
from fa.orchestrator import run_round
from fa.plans.playbooks import PARAM_RANGES


def _warm_attacker_cache(cache_root: Path, playbook: str, seed: int, model: str) -> None:
    """A deterministic stand-in for a real LLM call, same shape complete_json
    would cache: the schema's midpoint values for `playbook`."""
    schema = _param_schema(playbook)
    prompt = _prompt(playbook, seed)
    ck = cache_key(model, prompt, schema)
    midpoint = {name: (lo + hi) / 2 for name, (lo, hi) in PARAM_RANGES[playbook].items()}
    put(ck, midpoint, cache_root / "attacker")


def test_p1_round_ends_active_with_valid_ledger(monkeypatch, tmp_path):
    """The whole loop on temporary stores: attack -> defend -> gates -> second person approves ->
    ledger entry -> rollback. The LLM provider is a stand-in that answers from each schema."""
    import warnings

    from fa import orchestrator
    from fa.agents import llm
    from fa.release import approve, rollback, versions
    from fa.release.versions import ReleaseError, VersionStore
    from fa.verify import regression
    from fa.verify.regression import RegressionStore

    warnings.filterwarnings("ignore")
    store = VersionStore(tmp_path / "rules")
    monkeypatch.setattr(versions, "_default", store)
    monkeypatch.setattr(regression, "_default", RegressionStore(tmp_path / "reg.json"))
    base = load_config()
    cfg = base.model_copy(update={"llm_api_key": "gsk_test", "params": {
        **base.params, "agents": {**base.section("agents"), "cache_dir": str(tmp_path / "cache")},
        "search": {**base.section("search"), "trials": 12}}})
    monkeypatch.setattr(llm, "load_config", lambda *a, **k: cfg)
    monkeypatch.setattr(orchestrator, "load_config", lambda *a, **k: cfg)
    monkeypatch.setattr(llm, "_call_groq", lambda prompt, schema, model, key: llm._offline_answer(schema, "e2e"))

    orchestrator.run_round("P1", "alice")
    (patch,) = store.list_patches()
    assert patch["state"] == versions.AWAITING_APPROVAL
    assert [g["gate"] for g in patch["gates"]] == ["G1", "G2", "G3", "G4", "G5", "G6"]
    assert all(g["passed"] for g in patch["gates"])
    assert regression.all(), "the worst-case plan is stored for G3 next time"

    ledger = []
    led = lambda action, payload: ledger.append((action, payload)) or len(ledger)  # noqa: E731
    with pytest.raises(ReleaseError):                                  # the round starter cannot approve
        approve.approve(patch["id"], "alice", store=store, ledger=led)
    done = approve.approve(patch["id"], "bob", store=store, ledger=led)
    assert done["state"] == versions.ACTIVE and store.active_version() == "v2" and done["ledger_seq"] == 1
    assert ledger[0][0] == "promote" and ledger[0][1]["checker"] == "bob" and ledger[0][1]["gates"]["G5"] == "pass"

    rollback.rollback("v1", "bob", store=store, ledger=led)
    assert store.active_version() == "v1" and [a for a, _ in ledger] == ["promote", "rollback"]
    assert store.list_versions() == ["v1", "v2"]


def test_round_runs_select_plan_search_evaluate_for_real(monkeypatch, tmp_path):
    """SELECT (rules.loader.active), PLAN (attacker, via a pre-warmed cache
    entry standing in for a real LLM call), SEARCH (Optuna vs the real
    engine) and EVALUATE (regression.add) all now run against real M3/M4
    code, and DEFEND now gets real candidates from fa.ml.mine_rules. With no
    defender text in the (tmp) LLM cache and no API key, the round stops at
    the defender's LLM call with the documented clear cache-miss error.
    """
    real_config = load_config()
    seed = real_config.section("common").get("seed", 42)
    model = real_config.llm_model

    # A fresh Config, not the shared lru_cache'd singleton: mutating that in
    # place would leak this test's tmp_path cache_dir into every later test
    # in the session. Only fa.agents.llm needs the tmp cache_dir -- that's
    # the only place it reads it.
    patched = real_config.model_copy(
        update={
            "params": {**real_config.params, "agents": {**real_config.section("agents"), "cache_dir": str(tmp_path)}},
            "llm_api_key": None,
        }
    )
    monkeypatch.setattr("fa.agents.llm.load_config", lambda *a, **kw: patched)

    _warm_attacker_cache(tmp_path, "P1", seed, model)

    with pytest.raises(RuntimeError, match="LLM cache miss for key='defender'"):
        run_round("P1", started_by="pytest")
