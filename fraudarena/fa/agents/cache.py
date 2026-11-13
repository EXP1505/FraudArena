"""Owner: M1. File-backed cache for fa.agents.llm.complete_json, keyed by
SHA-256(model, prompt, schema), stored under params.yaml agents.cache_dir.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path


def cache_key(model: str, prompt: str, schema: dict) -> str:
    canonical = json.dumps(
        {"model": model, "prompt": prompt, "schema": schema}, sort_keys=True, separators=(",", ":")
    )
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _path_for(key: str, cache_dir: Path) -> Path:
    return cache_dir / f"{key}.json"


def get(key: str, cache_dir: Path) -> dict | None:
    path = _path_for(key, cache_dir)
    if not path.exists():
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def put(key: str, value: dict, cache_dir: Path) -> None:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _path_for(key, cache_dir)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(value, f, sort_keys=True, indent=2)
