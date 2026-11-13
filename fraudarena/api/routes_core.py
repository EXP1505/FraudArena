"""Owner: M2. GET /health, POST /tx, GET /decisions."""
from __future__ import annotations

import os
import time
import json
from typing import Any, Dict, List, Optional
from fastapi import APIRouter

from api.db import insert_event, get_decisions as db_get_decisions
from fa.contracts import Event, Decision
from fa.core.state import new_state, apply
from fa.core.engine import decide_with_features   # M4's engine: the one decision implementation
from fa.rules.loader import active as active_rule_set  # M4's version store: promote/rollback land here
from api.enrich import enrich, policy_pack

router = APIRouter()

# Global state instance for simulated bank in-process
_sim_state = new_state()

@router.get("/health")
def health() -> dict:
    return {"ok": True, "version": active_rule_set().version}

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

    # Features + decision + state update in one call, under the ACTIVE rule set
    # (the version store M4's approve/rollback moves), so a promoted rule takes effect here.
    rs = active_rule_set()
    decision, features = decide_with_features(_sim_state, ev_dict, rs)
    decision_action, fired = decision.decision, decision.fired
    version = int(rs.version.lstrip("v")) if rs.version.lstrip("v").isdigit() else 1

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

    by_id = {r.id: r for r in rs.rules}
    reasons = []
    for rid in fired:
        r = by_id.get(rid)
        if r is not None:
            e = enrich(r.model_dump(mode="json"))
            reasons.append({"rule_id": rid, "title": e["title"], "customer_message": e["customer_message"],
                            "treatment": e["treatment"]})

    return {
        "event_id": ev_dict.get("event_id", ""),
        "reasons": reasons,
        "action": decision_action,
        "decision": decision_action,
        "fired": fired,
        "version": rs.version,
        "latency_us": latency_us,
        "features": features
    }

@router.get("/decisions")
def get_decisions(run_id: str | None = None, limit: int = 100) -> list[dict]:
    return db_get_decisions(run_id=run_id, limit=limit)


@router.get("/api/model")
def model_status() -> dict:
    """Which data the thresholds come from: none (simulation), rehearsal, or real RBIH bundle."""
    from fa.rbih import status
    try:
        return status()
    except Exception as e:  # never break the dashboard over the badge
        return {"mode": "none", "dataset": "", "rehearsal": False, "verified": False, "metrics": {}, "installed_at": None, "error": str(e)}


@router.get("/api/policy")
def policy() -> dict:
    """The RBIH-calibrated policy pack (R1-R7): plain text, regulatory basis and per-rule evidence."""
    return {"rules": [enrich(r) for r in policy_pack()]}
