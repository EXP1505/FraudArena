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


@pytest.mark.skip(
    reason="blocked on fa.ml.mine_rules.candidates (M3) and fa.world.golden.golden_cases "
    "(M3, needed by gate G6) and fa.ledger.chain (M2) -- none implemented yet"
)
def test_p1_round_ends_active_with_valid_ledger():
    raise NotImplementedError


def test_round_runs_select_plan_search_evaluate_for_real(monkeypatch, tmp_path):
    """SELECT (rules.loader.active), PLAN (attacker, via a pre-warmed cache
    entry standing in for a real LLM call), SEARCH (Optuna vs the real
    engine) and EVALUATE (regression.add) all now run against real M3/M4
    code. The round still can't finish: DEFEND calls
    fa.ml.mine_rules.candidates(), which is still M3's NotImplementedError
    stub. That failure, at exactly that call, is the expected state until
    M3 lands it -- not a bug in this test.
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

    with pytest.raises(NotImplementedError):
        run_round("P1", started_by="pytest")
