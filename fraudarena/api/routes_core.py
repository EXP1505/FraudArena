"""Owner: M2. GET /health, POST /tx, GET /decisions."""
from __future__ import annotations

import os
import time
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter

from api.db import get_active_rule_version, get_rules_for_version, insert_event, get_decisions as db_get_decisions
from fa.contracts import Event, Decision
from fa.core.state import new_state, apply
from fa.core.features import compute_features

router = APIRouter()

# Global state instance for simulated bank in-process
_sim_state = new_state()

def _eval_op(val: Any, op: str, target: Any) -> bool:
    try:
        val = float(val) if isinstance(val, (int, float, str)) and str(val).replace('.', '', 1).isdigit() else val
        target = float(target) if isinstance(target, (int, float, str)) and str(target).replace('.', '', 1).isdigit() else target
        if op == "<": return val < target
        if op == "<=": return val <= target
        if op == ">": return val > target
        if op == ">=": return val >= target
        if op == "==": return val == target
    except Exception:
        return False
    return False

def decide(features: dict[str, float], rules: list[dict[str, Any]]) -> tuple[str, list[str]]:
    fired_block = []
    fired_hold = []

    for rule in rules:
        conds = rule.get("when", [])
        all_match = True
        for cond in conds:
            f_name = cond.get("f")
            op = cond.get("op")
            target = cond.get("v")
            f_val = features.get(f_name)
            if f_val is None or not _eval_op(f_val, op, target):
                all_match = False
                break
        if all_match:
            action = rule.get("action", "hold")
            if action == "block":
                fired_block.append(rule.get("id"))
            elif action == "hold":
                fired_hold.append(rule.get("id"))

    if fired_block:
        return "block", fired_block
    if fired_hold:
        return "hold", fired_hold
    return "allow", []

@router.get("/health")
def health() -> dict:
    v = get_active_rule_version()
    return {"ok": True, "version": f"v{v}" if isinstance(v, int) else str(v)}

@router.post("/tx")
def post_tx(event: dict) -> dict:
    t0 = time.perf_counter()

    # Normalise aliases
    ev_dict = dict(event)
    if "id" in ev_dict and "event_id" not in ev_dict:
        ev_dict["event_id"] = ev_dict["id"]
    if ev_dict.get("type") == "pay":
        ev_dict["type"] = "payment"
    elif ev_dict.get("type") == "payee_add":
        ev_dict["type"] = "add_payee"
    elif ev_dict.get("type") == "device_add":
        ev_dict["type"] = "login"

    # Compute features & decision
    features = compute_features(_sim_state, ev_dict)
    version = get_active_rule_version()
    rules = get_rules_for_version(version) or []

    decision_action, fired = decide(features, rules)

    # Mutate state
    apply(_sim_state, ev_dict, decision_action)

    latency_us = round((time.perf_counter() - t0) * 1_000_000, 2)

    # Persist in DB
    record = {
        "run_id": ev_dict.get("run_id", "default"),
        "ts": ev_dict.get("ts", 0),
        "account": ev_dict.get("account", ""),
        "type": ev_dict.get("type", "payment"),
        "amount": ev_dict.get("amount", 0),
        "payee": ev_dict.get("payee"),
        "device": ev_dict.get("device"),
        "action": decision_action,
        "rule_id": fired[0] if fired else None,
        "version": version,
        "features": features
    }
    insert_event(record)

    return {
        "event_id": ev_dict.get("event_id", ""),
        "action": decision_action,
        "decision": decision_action,
        "fired": fired,
        "version": f"v{version}",
        "latency_us": latency_us,
        "features": features
    }

@router.get("/decisions")
def get_decisions(run_id: str | None = None, limit: int = 100) -> list[dict]:
    return db_get_decisions(run_id=run_id, limit=limit)
