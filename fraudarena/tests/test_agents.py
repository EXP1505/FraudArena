"""Owner: M1. LLM cache hit test (second identical call hits cache with
network off), the worst-case search against the real engine (M4 landed),
and a defender fuzz test (never emits a rule with an unknown feature or
operator -- enforced by fa.contracts.Cond's own validator).
"""
from __future__ import annotations

import pytest

from fa import config as config_mod
from fa.agents import cache, llm
from fa.agents.defender import _assemble_rule
from fa.agents.search import get_plan, random_search_baseline, worst_case
from fa.config import Config
from fa.contracts import Cond, Rule
from fa.rules.loader import load_baseline


@pytest.fixture
def no_network_config(tmp_path, monkeypatch):
    cfg = Config(
        params={"agents": {"cache_dir": str(tmp_path)}},
        database_url="sqlite://unused",
        llm_api_key=None,
        llm_model="claude-sonnet-5-5",
    )
    monkeypatch.setattr(config_mod, "load_config", lambda *a, **kw: cfg)
    monkeypatch.setattr(llm, "load_config", lambda *a, **kw: cfg)
    return cfg


def test_llm_cache_hit_offline(no_network_config, tmp_path):
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    key = "attacker"
    ck = cache.cache_key(no_network_config.llm_model, "hello", schema)
    cache.put(ck, {"x": 42}, tmp_path / key)

    result = llm.complete_json("hello", schema, key)
    assert result == {"x": 42}


def test_llm_cache_miss_offline_raises_clear_error(no_network_config):
    schema = {"type": "object", "properties": {"x": {"type": "integer"}}}
    with pytest.raises(RuntimeError, match="LLM_API_KEY"):
        llm.complete_json("never cached", schema, "attacker")


def test_worst_case_finds_a_real_loss_against_baseline_v1():
    rs = load_baseline()
    trace = worst_case("P1", rs, trials=15, seed=3)
    assert trace.loss_through > 0

    plan = get_plan(trace.plan_id)
    assert plan is not None and plan.plan_id == trace.plan_id


def test_each_trial_gets_a_distinct_plan_id():
    """Regression: trials used to share one plan_id (seed never varied per
    trial), so every trial overwrote the same _PLAN_CACHE entry and would
    have corrupted G3's regression-set dedup by plan_id."""
    rs = load_baseline()
    random_search_baseline("P1", rs, trials=8, seed=11)
    # can't see every trial's plan_id directly, but the cache must hold more
    # than one entry after 8 trials with 8 different sampled parameter sets
    from fa.agents.search import _PLAN_CACHE

    assert len({k for k in _PLAN_CACHE if k.startswith("pl-P1-")}) > 1


def test_defender_rule_assembly_rejects_unknown_feature():
    candidate = {
        "conds": [{"f": "not_a_real_feature", "op": ">=", "v": 1}],
        "action": "hold",
        "evidence": {},
    }
    text = {"id": "R-bad", "rationale": "x", "expected_effect": "x"}
    with pytest.raises(ValueError, match="unknown feature"):
        _assemble_rule(candidate, text, version="v2")


def test_defender_rule_assembly_builds_valid_rule():
    candidate = {
        "conds": [{"f": "amount_ratio_30d", "op": ">=", "v": 8}],
        "action": "hold",
        "evidence": {"support": 10},
    }
    text = {"id": "R-ok", "rationale": "data-derived threshold", "expected_effect": "stops drains"}
    rule = _assemble_rule(candidate, text, version="v2")
    assert isinstance(rule, Rule) and rule.when == [Cond(f="amount_ratio_30d", op=">=", v=8)]
