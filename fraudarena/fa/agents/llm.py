"""Owner: M1. complete_json(prompt, schema, key) -> dict; cached, offline-safe.

Cache key = SHA-256(model, prompt, schema); `key` namespaces the cache (one
subfolder per call site, e.g. "attacker", "defender") so different agents
never collide even on an identical prompt. On a cache miss with no
LLM_API_KEY set (no network credentials), raises a clear RuntimeError
rather than hanging or returning garbage -- the demo always runs against a
pre-warmed cache (scripts/warm_cache.py).

Providers (no SDK dependency, plain httpx):
  anthropic (default)  Messages API, forcing one tool call shaped like `schema`.
  groq                 OpenAI-compatible chat completions in JSON mode. Selected by
                       LLM_PROVIDER=groq, or automatically when the key starts with "gsk_".
                       Set LLM_MODEL to a Groq model id (default llama-3.3-70b-versatile).
Either way the result is validated against the caller's required keys.
"""
from __future__ import annotations

import json
import os
import time
from pathlib import Path

import httpx

from fa.agents.cache import cache_key, get, put
from fa.config import load_config

ANTHROPIC_API_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"
RESPOND_TOOL_NAME = "respond"
GROQ_API_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_DEFAULT_MODEL = "llama-3.3-70b-versatile"


def _provider(api_key: str) -> str:
    p = (os.environ.get("LLM_PROVIDER") or "").strip().lower()
    if p in ("anthropic", "groq"):
        return p
    return "groq" if api_key.startswith("gsk_") else "anthropic"


def _call_groq(prompt: str, schema: dict, model: str, api_key: str) -> dict:
    system = ("Reply with ONE JSON object only, no prose, that matches this JSON schema: "
              + json.dumps(schema))
    payload = {
        "model": model,
        "temperature": 0,
        "response_format": {"type": "json_object"},
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
    }
    for attempt in range(4):                      # free tiers cap tokens per minute: wait and retry on HTTP 429
        resp = httpx.post(GROQ_API_URL, json=payload, timeout=60,
                          headers={"Authorization": f"Bearer {api_key}", "content-type": "application/json"})
        if resp.status_code != 429 or attempt == 3:
            break
        try:
            wait = float(resp.headers.get("retry-after") or 0)
        except ValueError:
            wait = 0
        time.sleep(min(max(wait, 8.0) + attempt * 4, 30))
    if resp.status_code >= 400:
        raise RuntimeError(f"Groq HTTP {resp.status_code} for model {model!r}: {resp.text[:300]}")
    text = resp.json()["choices"][0]["message"]["content"]
    try:
        return json.loads(text)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"Groq response was not valid JSON: {text[:200]!r}") from exc


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


def _offline_answer(schema: dict, ck: str) -> dict:
    """Deterministic stand-in used only when LLM_OFFLINE_FALLBACK=1 and there is no key/cache:
    numbers take the midpoint of their range, text fields get a fixed explanation."""
    out: dict = {}
    for name, spec in schema.get("properties", {}).items():
        if spec.get("type") == "number" and "minimum" in spec and "maximum" in spec:
            out[name] = (spec["minimum"] + spec["maximum"]) / 2
        elif name == "id":
            out[name] = f"AUTO-{ck[:6]}"
        elif name == "rationale":
            out[name] = "Mined from validation-traffic quantiles; offline mode, no LLM wording."
        elif name == "expected_effect":
            out[name] = "Holds the missed step; added friction is bounded by gate G5."
        elif spec.get("type") == "number":
            out[name] = 0
        else:
            out[name] = "offline"
    return out


def complete_json(prompt: str, schema: dict, key: str) -> dict:
    config = load_config()
    model = config.llm_model
    cache_root = Path(config.section("agents").get("cache_dir", "data/llm_cache"))
    cache_dir = cache_root / key

    ck = cache_key(model, prompt, schema)
    cached = get(ck, cache_dir)
    if cached is not None:
        return cached

    if not config.llm_api_key and os.environ.get("LLM_OFFLINE_FALLBACK", "").lower() in ("1", "true", "yes"):
        return _offline_answer(schema, ck)  # deliberately not cached: a real answer can replace it later

    if not config.llm_api_key:
        raise RuntimeError(
            f"LLM cache miss for key={key!r} (hash {ck[:12]}...) and no LLM_API_KEY set. "
            "Set LLM_API_KEY and run scripts/warm_cache.py, or supply a pre-warmed cache."
        )

    if _provider(config.llm_api_key) == "groq":
        result = _call_groq(prompt, schema, model, config.llm_api_key)
    else:
        result = _call_anthropic(prompt, schema, model, config.llm_api_key)
    missing = [k for k in schema.get("required", []) if k not in result]
    if missing:
        raise RuntimeError(f"LLM answer is missing required keys {missing}: {result!r}")
    put(ck, result, cache_dir)
    return result
