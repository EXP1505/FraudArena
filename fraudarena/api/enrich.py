"""Owner: M2 (Person B). Attach plain-language text to rules at response time.

Rules stored before the policy pack existed (baseline v1, defender patches) carry no
title / customer message. This fills the gaps from fa.rules.explain, and takes the regulatory
references of the canonical rules R1-R7 from the policy pack. Nothing here changes decisions.
"""
from __future__ import annotations

from functools import lru_cache
from typing import Any

from fa.rules.explain import explain


@lru_cache(maxsize=1)
def _pack() -> dict[str, dict]:
    try:
        from fa.rules.policy_pack import build
        return {r.id: r.model_dump(mode="json") for r in build()}
    except Exception:
        return {}


def policy_pack() -> list[dict]:
    return list(_pack().values())


def enrich(rule: dict[str, Any] | None) -> dict[str, Any] | None:
    if not rule:
        return rule
    out = dict(rule)
    try:
        text = explain(out)
    except Exception:
        text = {}
    for k in ("title", "customer_message", "analyst_note", "treatment"):
        if not out.get(k):
            out[k] = text.get(k, "")
    if not out.get("reg_refs"):
        out["reg_refs"] = _pack().get(out.get("id", ""), {}).get("reg_refs", [])
    return out
