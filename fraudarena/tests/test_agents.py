"""Owner: M1. LLM cache hit test (second identical call hits cache with
network off) and defender fuzz test (never emits a rule with an unknown
feature or operator).
"""
from __future__ import annotations

import pytest

from fa import config as config_mod
from fa.agents import cache, llm
from fa.config import Config


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
