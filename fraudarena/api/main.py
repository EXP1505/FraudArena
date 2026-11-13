# Owner: M2. FastAPI app: POST /tx, GET /decisions, GET /health.
import os
import json
import time
import logging
from contextlib import asynccontextmanager
from typing import Any, Dict, List, Optional
from fastapi import FastAPI, Query, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware

from api.db import init_db, get_active_rule_version, get_rules_for_version, save_rule_version, insert_event, get_decisions
from fa.contracts import Event, Decision

logger = logging.getLogger("fa.api")
logging.basicConfig(level=logging.INFO)

# Path to baseline rules
RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "rules", "baseline_v1.json")

# In-memory simulator fallback state if M3/M4 are not loaded yet
_in_memory_state: Dict[str, Any] = {
    "accounts": {},
    "inflows": {},
    "outflows": {}
}

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

def _fallback_compute_features(event: Event, state: Dict[str, Any]) -> Dict[str, Any]:
    acc_id = event.account
    acc = state["accounts"].setdefault(acc_id, {
        "balance": 1000000.0,
        "avg_30d": 10000.0,
        "payees": {},
        "devices": {},
        "recent_pays": []
    })

    amt = float(event.amount or 0.0)
    avg_30d = float(acc.get("avg_30d") or 10000.0)
    amount_ratio_30d = amt / avg_30d if avg_30d > 0 else 1.0

    payee_age_h = 0.0
    if event.payee:
        if event.payee in acc["payees"]:
            payee_age_h = max(0.0, (event.ts - acc["payees"][event.payee]) / 3600.0)
        else:
            payee_age_h = 0.0

    device_changed_24h = 0
    if event.device:
        if event.device in acc["devices"]:
            first_seen = acc["devices"][event.device]
            if (event.ts - first_seen) <= 86400:
                device_changed_24h = 1
        else:
            device_changed_24h = 1

    one_hour_ago = event.ts - 3600
    twenty_four_hours_ago = event.ts - 86400

    recent_pays = acc.get("recent_pays", [])
    pays_1h = [p for p in recent_pays if p[0] >= one_hour_ago]
    pays_24h = [p for p in recent_pays if p[0] >= twenty_four_hours_ago]

    n_pay_1h = len(pays_1h)
    n_pay_24h = len(pays_24h)
    sum_1h = sum(p[1] for p in pays_1h)
    sum_24h = sum(p[1] for p in pays_24h)

    sum_newpayee_1h = sum(
        p[1] for p in pays_1h
        if p[2] in acc["payees"] and (event.ts - acc["payees"][p[2]]) < 86400
    )

    payees_1h = {p[2] for p in pays_1h if p[2]}
    if event.payee:
        payees_1h.add(event.payee)
    fan_out_1h = len(payees_1h)

    r_fan_in_24h = 0
    r_passthrough_1h = 0.0
    if event.payee:
        inflows = state["inflows"].get(event.payee, [])
        senders_24h = {inf[1] for inf in inflows if inf[0] >= twenty_four_hours_ago}
        r_fan_in_24h = len(senders_24h)

    hour_of_day = (event.ts // 3600) % 24
    night_flag = 1 if 0 <= hour_of_day < 5 else 0

    return {
        "amount_ratio_30d": round(amount_ratio_30d, 4),
        "payee_age_h": round(payee_age_h, 4),
        "device_changed_24h": device_changed_24h,
        "n_pay_1h": n_pay_1h,
        "n_pay_24h": n_pay_24h,
        "sum_1h": sum_1h,
        "sum_24h": sum_24h,
        "sum_newpayee_1h": sum_newpayee_1h,
        "fan_out_1h": fan_out_1h,
        "r_fan_in_24h": r_fan_in_24h,
        "r_passthrough_1h": round(r_passthrough_1h, 4),
        "hour_of_day": hour_of_day,
        "night_flag": night_flag
    }

def _fallback_decide(features: Dict[str, Any], rules: List[Dict[str, Any]]) -> tuple[str, Optional[str]]:
    fired_block = []
    fired_hold = []

    for rule in rules:
        conds = rule.get("when", [])
        all_match = True
        for cond in conds:
            feat_val = features.get(cond["f"])
            if feat_val is None or not _eval_op(feat_val, cond["op"], cond["v"]):
                all_match = False
                break
        if all_match:
            action = rule.get("action", "hold")
            if action == "block":
                fired_block.append(rule.get("id"))
            elif action == "hold":
                fired_hold.append(rule.get("id"))

    if fired_block:
        return "block", fired_block[0]
    if fired_hold:
        return "hold", fired_hold[0]
    return "allow", None

def _fallback_apply(event: Event, state: Dict[str, Any], decision_action: str):
    acc = state["accounts"].setdefault(event.account, {
        "balance": 1000000.0,
        "avg_30d": 10000.0,
        "payees": {},
        "devices": {},
        "recent_pays": []
    })

    if event.type in ("payee_add", "add_payee") and event.payee:
        acc["payees"].setdefault(event.payee, event.ts)

    if event.type in ("device_add", "add_device", "login") and event.device:
        acc["devices"].setdefault(event.device, event.ts)

    if event.type in ("pay", "payment") and decision_action == "allow":
        amt = float(event.amount or 0.0)
        acc["balance"] -= amt
        acc["recent_pays"].append((event.ts, amt, event.payee or ""))
        if event.payee:
            inflows = state["inflows"].setdefault(event.payee, [])
            inflows.append((event.ts, event.account, amt))

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Initialize DB schema
    init_db()

    # Load baseline_v1.json into rule_versions if missing
    active_v = get_active_rule_version()
    existing_rules = get_rules_for_version(1)
    if not existing_rules:
        baseline_rules = []
        if os.path.exists(RULES_PATH):
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                baseline_rules = json.load(f)
        else:
            # Fallback baseline rules (R1 to R6)
            baseline_rules = [
                {"id": "R1", "action": "hold", "when": [{"f": "amount_ratio_30d", "op": ">=", "v": 10.0}]},
                {"id": "R2", "action": "hold", "when": [{"f": "payee_age_h", "op": "<", "v": 1.0}, {"f": "amount_ratio_30d", "op": ">=", "v": 3.0}]},
                {"id": "R3", "action": "block", "when": [{"f": "n_pay_1h", "op": ">=", "v": 12.0}]},
                {"id": "R4", "action": "hold", "when": [{"f": "device_changed_24h", "op": "==", "v": 1}, {"f": "sum_1h", "op": ">=", "v": 50000.0}]},
                {"id": "R5", "action": "block", "when": [{"f": "fan_out_1h", "op": ">=", "v": 8.0}]},
                {"id": "R6", "action": "hold", "when": [{"f": "night_flag", "op": "==", "v": 1}, {"f": "amount_ratio_30d", "op": ">=", "v": 6.0}]}
            ]
        save_rule_version(1, baseline_rules, source="baseline")
        logger.info("Loaded baseline_v1 rules into rule_versions table (version 1).")
    yield

app = FastAPI(title="FraudArena API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.get("/health")
def health():
    """Health check endpoint: returns rule version and status."""
    v = get_active_rule_version()
    return {"ok": True, "rule_version": v}

@app.post("/tx", response_model=Decision)
def process_transaction(event: Event, run_id: Optional[str] = "run_default"):
    """
    POST /tx: receives an event, computes features, decides allow/hold/block,
    applies decision to state, and persists the event decision to the database.
    """
    t0 = time.perf_counter()

    # Determine active rules
    version = get_active_rule_version()
    rules = get_rules_for_version(version) or []

    # Check if M3 / M4 core modules are available
    try:
        from fa.core.features import compute_features
        from fa.core.engine import decide, apply
        from fa.core.state import get_global_state
        state = get_global_state()
        features = compute_features(state, event)
        action, rule_id = decide(features, rules)
        apply(state, event, action)
    except Exception:
        # Fallback in-process engine
        features = _fallback_compute_features(event, _in_memory_state)
        action, rule_id = _fallback_decide(features, rules)
        _fallback_apply(event, _in_memory_state, action)

    latency_us = int((time.perf_counter() - t0) * 1_000_000)

    # Persist in events table
    event_id = event.event_id or event.id or f"e-{int(time.time()*1000)}"
    insert_event(
        run_id=run_id,
        ts=event.ts,
        account=event.account,
        type_=event.type,
        amount=event.amount,
        payee=event.payee,
        device=event.device,
        action=action,
        rule_id=rule_id,
        version=version,
        features=features
    )

    return Decision(
        event_id=event_id,
        action=action,
        rule_id=rule_id,
        version=version,
        features=features,
        latency_us=latency_us
    )

@app.get("/decisions")
def list_decisions(run_id: Optional[str] = None, limit: int = 50):
    """Retrieve recent decisions recorded in the database."""
    return get_decisions(run_id=run_id, limit=limit)

@app.get("/rules")
def get_rules(version: Optional[int] = None):
    """Get active rules JSON for inspection."""
    v = version or get_active_rule_version()
    return {"version": v, "rules": get_rules_for_version(v)}
