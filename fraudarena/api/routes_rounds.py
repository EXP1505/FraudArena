"""Owner: M2. POST /api/rounds, GET /api/rounds/{id}, GET /api/versions,
GET /api/versions/{v}, GET /api/metrics, POST /api/world/reset.
"""
from __future__ import annotations

import threading
import uuid
from typing import Optional

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from api import auth, credits
from api.db import (
    get_metrics_records,
    get_round as db_get_round,
    list_rounds as db_list_rounds,
    save_metric,
    save_round,
)
from fa.core.state import new_state
from fa.release.versions import default_store

from api.enrich import enrich

router = APIRouter(prefix="/api")


class PostRoundRequest(BaseModel):
    playbook: str = "P1"
    started_by: str = "arena-ui"


def _background_round(round_id: str, playbook: str, started_by: str) -> None:
    try:
        from fa.orchestrator import run_round_detailed

        save_round(round_id, playbook, started_by, "RUNNING")
        # Same id end to end, so the browser polls the row that gets the real outcome:
        # DONE | NO_SAFE_PATCH | AWAITING_APPROVAL | REJECTED_BY_GATES
        _id, outcome = run_round_detailed(playbook, started_by, round_id=round_id)
        save_round(round_id, outcome.get("playbook", playbook), started_by, outcome["state"])
    except NotImplementedError:
        # Expected if downstream candidate miner is still a stub
        save_round(round_id, playbook, started_by, "STOPPED_AT_DEFEND")
    except Exception as exc:
        save_round(round_id, playbook, started_by, f"ERROR: {str(exc)[:300]}")


@router.post("/rounds")
def post_round(request: Request, req: Optional[PostRoundRequest] = None, playbook: Optional[str] = None) -> dict:
    """Start an adversarial round. Runs search, red-team attack, and defender proposal."""
    pb = (req.playbook if req else None) or playbook or "P1"
    starter = (req.started_by if req else None) or "arena-ui"
    round_id = f"rnd-{uuid.uuid4().hex[:8]}"

    user, cost = auth.current_email(request), credits.cost_of(pb)
    try:
        balance = credits.charge(user, cost, f"Round: {'new AI attack' if pb == 'NEW' else pb}", ref=round_id)
    except credits.OutOfCredits as exc:
        raise HTTPException(status_code=402, detail=str(exc))

    save_round(round_id, pb, starter, "STARTED")

    def work() -> None:
        _background_round(round_id, pb, starter)
        credits.refund_if_failed(user, cost, round_id)

    # Run in thread so client receives immediate round_id for polling
    t = threading.Thread(target=work, daemon=True)
    t.start()

    return {"credits_charged": cost, "credits_left": balance,
        "round_id": round_id,
        "playbook": pb,
        "status": "started",
        "started_by": starter,
    }


def _decided(row: dict) -> dict:
    """A round stays AWAITING_APPROVAL in the database. Once its patch is approved or rejected the API
    reports the real outcome, so the dashboard never says "waiting" about a decision already made."""
    if row and row.get("state") == "AWAITING_APPROVAL":
        for p in default_store().list_patches():
            if p.get("round_id") == row.get("id"):
                outcome = {"ACTIVE": "APPROVED", "REJECTED": "REJECTED"}.get(p.get("state"))
                if outcome == "REJECTED" and str(p.get("reason", "")).startswith("Superseded"):
                    outcome = "SUPERSEDED"
                if outcome:
                    return {**row, "state": outcome, "patch_id": p["id"]}
                return {**row, "patch_id": p["id"]}
    return row


@router.get("/rounds")
def list_rounds() -> list[dict]:
    """List recent rounds."""
    return [_decided(r) for r in db_list_rounds()]


@router.get("/rounds/{round_id}")
def get_round(round_id: str) -> dict:
    """Get the live status and details of a round."""
    r = db_get_round(round_id)
    if not r:
        raise HTTPException(status_code=404, detail=f"Round {round_id} not found")
    return _decided(r)


@router.get("/rounds/{round_id}/nofix")
def get_nofix(round_id: str) -> dict:
    """Why a round ended with no safe fix: the closest candidate, what is wrong with it, and ideas for a person."""
    from fa.release import nofix

    report = nofix.get(round_id)
    if report is None:
        raise HTTPException(status_code=404, detail=f"No explanation stored for round {round_id}")
    return report


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
            diff = [enrich(r.model_dump(mode="json")) for r in rs.rules if r.id not in parent_ids]
        except Exception:
            pass

    return {
        "version": version,
        "active": version == active_v,
        "rules": [enrich(r.model_dump(mode="json")) for r in rs.rules],
        "diff_vs_parent": diff,
    }


_measuring: set[str] = set()
_random_baseline: dict[str, int] = {}
_measure_lock = threading.Lock()


def _measure(jobs: dict[str, list[str]]) -> None:
    """Measure rule versions for real and store the rows. `jobs` maps a version to the playbooks to attack: only the
    playbooks someone has actually run are measured. With none, just the friction on normal traffic is measured.
    Slow, so it runs in a background thread."""
    from fa.metrics import experiment, normal_friction

    store = default_store()
    try:
        for v, pbs in jobs.items():
            if pbs:
                rows = experiment(store.get(v), v, playbooks=pbs)
                for r in rows:
                    save_metric(r["version"], r["playbook"], int(r["wcel"]), float(r["hold_rate"]),
                                float(r["hold_rate_lo"]), float(r["hold_rate_hi"]), int(r["detection_delay_s"] or 0))
                _random_baseline[v] = max([_random_baseline.get(v, 0), *(int(r["random_wcel"]) for r in rows)])
            else:
                fr = normal_friction(None, "validation", store.get(v))
                save_metric(v, "_friction", 0, float(fr["rate"]), float(fr["lo"]), float(fr["hi"]), 0)
    except Exception:
        pass  # leave unmeasured; the dashboard keeps showing "measuring"
    finally:
        with _measure_lock:
            for v in jobs:
                _measuring.discard(v)


@router.get("/metrics")
def get_metrics() -> dict:
    """Measured WCEL per playbook, hold rate with Wilson CI, and history per version.

    Nothing here is hard-coded: if the active version (or v1, the baseline) has no metrics rows
    yet, a background measurement starts and `measuring` is true until the rows exist."""
    store = default_store()
    active_v = store.active_version()
    rounds = db_list_rounds()
    if not rounds:
        # Nothing is measured until someone presses Run: the dashboard starts empty and fills in from the first round.
        return {"active_version": active_v, "history": [], "measured": False, "measuring": False, "waiting_for_first_round": True, "played": [],
                "summary": {"wcel_p1": None, "wcel_p2": None, "wcel_p3": None, "hold_rate_pct": None, "random_baseline_wcel": None}}
    # Only the attack types that were actually run get measured: running P1 must not fill in P2 and P3.
    played = [p for p in ("P1", "P2", "P3") if any(r.get("playbook") == p for r in rounds)]
    rows = get_metrics_records()
    have: dict[str, set[str]] = {}
    for r in rows:
        have.setdefault(r["version"], set()).add(r["playbook"])
    jobs: dict[str, list[str]] = {}
    for v in dict.fromkeys(["v1", active_v]):
        missing = [p for p in played if p not in have.get(v, set())]
        if missing or (not played and v not in have):
            jobs[v] = missing
    with _measure_lock:
        jobs = {v: pbs for v, pbs in jobs.items() if v not in _measuring}
        _measuring.update(jobs)
    if jobs:
        threading.Thread(target=_measure, args=(jobs,), daemon=True).start()

    mine = {r["playbook"]: r for r in rows if r["version"] == active_v}
    first = next(iter(mine.values()), None)
    summary = {
        "wcel_p1": mine["P1"]["wcel"] if "P1" in mine else None,
        "wcel_p2": mine["P2"]["wcel"] if "P2" in mine else None,
        "wcel_p3": mine["P3"]["wcel"] if "P3" in mine else None,
        "hold_rate_pct": round(first["hold_rate"] * 100, 3) if first else None,
        "random_baseline_wcel": _random_baseline.get(active_v),
    }
    return {
        "active_version": active_v,
        "history": rows,
        "summary": summary,
        "played": played,
        "measured": bool(mine) and all(p in mine for p in played),
        "measuring": active_v in _measuring or "v1" in _measuring,
    }


@router.post("/world/reset")
def reset_world() -> dict:
    """Clean slate: active rules back to v1; rounds, patches, versions above v1, regression plans
    and non-v1 metrics cleared. The ledger is kept (audit trail) and gets a `world_reset` entry."""
    import shutil
    from pathlib import Path

    from api.db import reset_run_data

    from api.routes_export import snapshot_rulebook
    snapshot = snapshot_rulebook("before-reset")   # signed JSON + PDF of the verified rulebook, kept on disk

    store = default_store()
    removed = {"versions": 0, "patches": 0}
    try:
        for f in (Path(store.root) / "versions").glob("v*.json"):
            if f.stem != "v1":
                f.unlink(); removed["versions"] += 1
        pdir = Path(store.root) / "patches"
        if pdir.exists():
            removed["patches"] = len(list(pdir.glob("pt-*.json")))
            shutil.rmtree(pdir)
        store.set_active("v1")
        from api import routes_export
        routes_export._stress.clear()
    except Exception:
        pass

    try:
        from fa.verify.regression import clear as clear_regression
        clear_regression()
    except Exception:
        pass
    try:
        from api import autopilot
        from fa.plans.invent import clear as clear_invented
        autopilot.stop()
        clear_invented()
        from fa.release.nofix import clear as clear_nofix
        clear_nofix()
        autopilot.reset()
    except Exception:
        pass

    cleared = {}
    try:
        cleared = reset_run_data()
    except Exception:
        pass
    for v in [k for k in _random_baseline if k != "v1"]:
        _random_baseline.pop(v, None)

    try:
        from api import routes_core
        routes_core._sim_state = new_state()
    except Exception:
        pass

    seq = None
    try:
        from fa.ledger.chain import append
        seq = append("world_reset", {"to": "v1", "cleared": {**removed, **cleared}}).seq
    except Exception:
        pass

    return {
        "status": "ok",
        "active_version": "v1",
        "cleared": {**removed, **cleared},
        "ledger_seq": seq,
        "snapshot": snapshot,
        "message": "World reset: v1 active, rounds and patches cleared. The ledger keeps its history.",
    }
