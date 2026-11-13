"""Owner: M1. complete_json(prompt, schema, key) -> dict; cached, offline-safe.

Cache key = SHA-256(model, prompt, schema); `key` namespaces the cache (one
subfolder per call site, e.g. "attacker", "defender") so different agents
never collide even on an identical prompt. On a cache miss with no
LLM_API_KEY set (no network credentials), raises a clear RuntimeError
rather than hanging or returning garbage -- the demo always runs against a
pre-warmed cache (scripts/warm_cache.py).

Uses the Anthropic Messages API directly over httpx (no extra SDK
dependency), forcing a single tool call shaped like `schema` so the result
is JSON that matches the caller's contract.
"""
from __future__ import annotations

from pathlib import Path

import httpx

from fa.agents.cache import cache_key, get, put
from fa.config import load_config

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
RESPOND_TOOL_NAME = "respond"


def _call_anthropic(prompt: str, schema: dict, model: str, api_key: str) -> dict:
    payload = {
        "model": model,
        "max_tokens": 2048,
        "temperature": 0,
        "messages": [{"role": "user", "content": prompt}],
        "tools": [
            {
                "name": RESPOND_TOOL_NAME,
                "description": "Return the answer as structured JSON matching the given schema.",
                "input_schema": schema,
            }
        ],
        "tool_choice": {"type": "tool", "name": RESPOND_TOOL_NAME},
    }
    headers = {
        "x-api-key": api_key,
        "anthropic-version": ANTHROPIC_VERSION,
        "content-type": "application/json",
    }
    resp = httpx.post(ANTHROPIC_API_URL, json=payload, headers=headers, timeout=60)
    resp.raise_for_status()
    body = resp.json()
    for block in body.get("content", []):
        if block.get("type") == "tool_use" and block.get("name") == RESPOND_TOOL_NAME:
            return block["input"]
    raise RuntimeError(f"LLM response had no {RESPOND_TOOL_NAME!r} tool call: {body!r}")


def complete_json(prompt: str, schema: dict, key: str) -> dict:
    config = load_config()
    model = config.llm_model
    cache_root = Path(config.section("agents").get("cache_dir", "data/llm_cache"))
    cache_dir = cache_root / key

    ck = cache_key(model, prompt, schema)
    cached = get(ck, cache_dir)
    if cached is not None:
        return cached

    if not config.llm_api_key:
        raise RuntimeError(
            f"LLM cache miss for key={key!r} (hash {ck[:12]}...) and no LLM_API_KEY set. "
            "Set LLM_API_KEY and run scripts/warm_cache.py, or supply a pre-warmed cache."
        )

    result = _call_anthropic(prompt, schema, model, config.llm_api_key)
    put(ck, result, cache_dir)
    return result
