"""Owner: M1. Loads params.yaml and environment variables into one Config.

params.yaml is split by top-level section, one owner per section (see
docs/TIMELINE.md golden rule 5): common (M1) / api (M2) / world, ml (M3) /
rules, verifier, release (M4) / search, agents (M1). Use Config.section(name)
to read your own section; never read another owner's section's raw dict from
outside this module's tests.
"""
from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

import yaml
from pydantic import BaseModel

PARAMS_PATH = Path(__file__).resolve().parent.parent / "params.yaml"


class Config(BaseModel):
    params: dict
    database_url: str
    llm_api_key: str | None = None
    llm_model: str = "claude-sonnet-5-5"

    def section(self, name: str) -> dict:
        return self.params.get(name, {}) or {}


def _pick_model() -> str:
    """LLM_MODEL if set; Groq keys (gsk_) default to a Groq model and never inherit a Claude model name."""
    key = os.environ.get("LLM_API_KEY") or ""
    model = os.environ.get("LLM_MODEL") or ""
    if key.startswith("gsk_"):
        return model if model and not model.startswith("claude") else "llama-3.3-70b-versatile"
    return model or "claude-sonnet-5-5"


@lru_cache
def load_config(params_path: str | None = None) -> Config:
    path = Path(params_path) if params_path else PARAMS_PATH
    with open(path, encoding="utf-8") as f:
        params = yaml.safe_load(f) or {}
    return Config(
        params=params,
        database_url=os.environ.get(
            "DATABASE_URL", "postgresql://postgres:fraudarena@localhost:5432/fraudarena"
        ),
        llm_api_key=os.environ.get("LLM_API_KEY"),
        llm_model=_pick_model(),
    )
