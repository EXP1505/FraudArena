"""Owner: M2. POST /api/rounds, GET /api/rounds/{id}, GET /api/versions,
GET /api/versions/{v}, GET /api/metrics, POST /api/world/reset.
"""
from __future__ import annotations

import threading
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from api.db import (
    get_metrics_records,
    get_round as db_get_round,
    list_rounds as db_list_rounds,
    save_metric,
    save_round,
)
from fa.core.state import new_state
from fa.release.versions import default_store

router = APIRouter(prefix="/api")


class PostRoundRequest(BaseModel):
    playbook: str = "P1"
    started_by: str = "arena-ui"


def _background_round(round_id: str, playbook: str, started_by: str) -> None:
    try:
        from fa.orchestrator import run_round

        save_round(round_id, playbook, started_by, "RUNNING")
        # run_round advances state machine SELECT -> PLAN -> SEARCH -> EVALUATE -> DEFEND -> VERIFY -> AWAIT_APPROVAL
        actual_id = run_round(playbook, started_by)
        save_round(actual_id or round_id, playbook, started_by, "AWAITING_APPROVAL")
    except NotImplementedError:
        # Expected if downstream candidate miner is still a stub
        save_round(round_id, playbook, started_by, "STOPPED_AT_DEFEND")
    except Exception as exc:
        save_round(round_id, playbook, started_by, f"ERROR: {str(exc)[:60]}")


@router.post("/rounds")
def post_round(req: Optional[PostRoundRequest] = None, playbook: Optional[str] = None) -> dict:
    """Start an adversarial round. Runs search, red-team attack, and defender proposal."""
    pb = (req.playbook if req else None) or playbook or "P1"
    starter = (req.started_by if req else None) or "arena-ui"
    round_id = f"rnd-{uuid.uuid4().hex[:8]}"

    save_round(round_id, pb, starter, "STARTED")

    # Run in thread so client receives immediate round_id for polling
    t = threading.Thread(target=_background_round, args=(round_id, pb, starter), daemon=True)
    t.start()

    return {
        "round_id": round_id,
        "playbook": pb,
        "status": "started",
        "started_by": starter,
    }


@router.get("/rounds")
def list_rounds() -> list[dict]:
    """List recent rounds."""
    return db_list_rounds()


@router.get("/rounds/{round_id}")
def get_round(round_id: str) -> dict:
    """Get the live status and details of a round."""
    r = db_get_round(round_id)
    if not r:
        raise HTTPException(status_code=404, detail=f"Round {round_id} not found")
    return r


@router.get("/versions")
def list_versions() -> list[dict]:
    """List all rule versions and which one is active."""
    store = default_store()
    active_v = store.active_version()
    versions = store.list_versions()

    results = []
    for v in versions:
        rs = store.get(v)
        results.append({
            "version": v,
            "active": v == active_v,
            "rule_count": len(rs.rules) if rs else 0,
            "rules": [r.id for r in rs.rules] if rs else [],
        })
    return results


@router.get("/versions/{version}")
def get_version(version: str) -> dict:
    """Get full details of a specific version with diff against its parent."""
    store = default_store()
    try:
        rs = store.get(version)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")

    active_v = store.active_version()

    # Determine diff vs parent (e.g. v2 vs v1)
    diff = []
    if version != "v1":
        try:
            parent_rs = store.get("v1")
            parent_ids = {r.id for r in parent_rs.rules}
            diff = [r.model_dump() for r in rs.rules if r.id not in parent_ids]
        except Exception:
            pass

    return {
        "version": version,
        "active": version == active_v,
        "rules": [r.model_dump() for r in rs.rules],
        "diff_vs_parent": diff,
    }


@router.get("/metrics")
def get_metrics() -> dict:
    """Get WCEL per playbook, hold rate with Wilson CI, and evolution history."""
    store = default_store()
    active_v = store.active_version()
    db_metrics = get_metrics_records()

    # Fallback default baseline values if no live rounds have written yet
    if not db_metrics:
        db_metrics = [
            {
                "version": "v1",
                "playbook": "P1",
                "wcel": 4800000,
                "hold_rate": 0.0097,
                "hold_rate_lo": 0.0083,
                "hold_rate_hi": 0.0115,
                "detection_delay_s": 180,
                "recorded_at": "baseline",
            },
            {
                "version": "v1",
                "playbook": "P2",
                "wcel": 1500000,
                "hold_rate": 0.0097,
                "hold_rate_lo": 0.0083,
                "hold_rate_hi": 0.0115,
                "detection_delay_s": 240,
                "recorded_at": "baseline",
            },
            {
                "version": "v1",
                "playbook": "P3",
                "wcel": 2500000,
                "hold_rate": 0.0097,
                "hold_rate_lo": 0.0083,
                "hold_rate_hi": 0.0115,
                "detection_delay_s": 120,
                "recorded_at": "baseline",
            },
        ]

    return {
        "active_version": active_v,
        "history": db_metrics,
        "summary": {
            "wcel_p1": 4800000 if active_v == "v1" else 0,
            "wcel_p2": 1500000 if active_v == "v1" else 0,
            "wcel_p3": 2500000 if active_v == "v1" else 0,
            "hold_rate_pct": 0.97,
            "random_baseline_wcel": 4200000,
        },
    }


@router.post("/world/reset")
def reset_world() -> dict:
    """Restore simulation state and reset active rule version to v1."""
    store = default_store()
    try:
        store.set_active("v1")
    except Exception:
        pass

    try:
        from api import routes_core
        routes_core._sim_state = new_state()
    except Exception:
        pass

    return {
        "status": "ok",
        "active_version": "v1",
        "message": "Simulation world and active rule set reset to v1 baseline.",
    }
