"""Owner: M2. Export / verify / import of rulebooks and the attack library, plus PDF.

Nothing imported ever goes live: rulebook rules become PROPOSED patches that must pass G1-G6 and a
second-person approval; attack plans only join the regression set after they replay cleanly.
"""
from __future__ import annotations

import json
import time
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from api.enrich import enrich
from fa.contracts import Plan, Rule
from fa.release import rulebook as rb
from fa.release.versions import default_store

router = APIRouter(prefix="/api")


def rulebook_pdf(doc: dict, ledger_ok: bool | None = None) -> bytes:
    """Imported lazily so the API still starts if reportlab is not installed (PDF then answers 503)."""
    try:
        from api.report import rulebook_pdf as _pdf
    except ImportError as exc:
        raise HTTPException(status_code=503, detail="PDF export needs reportlab: pip install reportlab") from exc
    return _pdf(doc, ledger_ok=ledger_ok)

_ROOT = Path(__file__).resolve().parents[1]


def _snap_dir() -> Path:
    import os
    return Path(os.environ.get("FA_SNAPSHOT_DIR", _ROOT / "data" / "snapshots"))



def _data_source() -> dict:
    try:
        from fa.rbih import status
        st = status()
        label = {"real": "RBIH NFPC Phase-2 (derived)", "rehearsal": "Simulation (rehearsal)"}.get(st.get("mode"), "Simulation")
        return {"mode": st.get("mode", "none"), "label": label, "dataset": st.get("dataset", ""), "verified": bool(st.get("verified"))}
    except Exception:
        return {"mode": "none", "label": "Simulation", "dataset": "", "verified": False}


def _approvals(store, version: str) -> list[dict]:
    """The patches that built this version (v1 is the baseline: none)."""
    out = []
    for p in store.list_patches():
        if p.get("state") == "ACTIVE" and p.get("new_version"):
            try:
                if int(p["new_version"].lstrip("v")) <= int(version.lstrip("v")):
                    g = p.get("gates") or []
                    out.append({"patch_id": p["id"], "rule_id": (p.get("rule") or {}).get("id"), "new_version": p["new_version"],
                                "gates": f"{sum(1 for x in g if x.get('passed'))}/{len(g) or 6}", "maker": p.get("maker"),
                                "starter": p.get("starter"), "checker": p.get("checker"), "ledger_seq": p.get("ledger_seq")})
            except ValueError:
                pass
    return sorted(out, key=lambda a: int(a["new_version"].lstrip("v")))


def build_doc(version: str) -> dict:
    store = default_store()
    try:
        rs = store.get(version)
    except KeyError:
        raise HTTPException(status_code=404, detail=f"Version {version} not found")
    meta = store.meta(version)
    doc = {"format": rb.RULEBOOK_FORMAT, "version": version, "parent": meta.get("parent"), "source": meta.get("source") or "baseline",
           "active": version == store.active_version(), "exported_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
           "data_source": _data_source(), "approvals": _approvals(store, version),
           "rules": [enrich(r.model_dump(mode="json")) for r in rs.rules]}
    return rb.seal(doc)


def _ledger_ok() -> bool | None:
    try:
        from fa.ledger.verify import verify
        return verify(table="ledger") is None
    except Exception:
        return None


def snapshot_rulebook(reason: str) -> dict | None:
    """Save the active rulebook (signed JSON + PDF) to data/snapshots/ so it survives a reset. Never raises."""
    try:
        v = default_store().active_version()
        doc = build_doc(v)
        SNAP_DIR = _snap_dir()
        SNAP_DIR.mkdir(parents=True, exist_ok=True)
        stem = f"rulebook-{v}-{time.strftime('%Y%m%d-%H%M%S', time.gmtime())}-{reason}"
        (SNAP_DIR / f"{stem}.json").write_text(json.dumps(doc, indent=1, ensure_ascii=False), encoding="utf-8")
        try:
            (SNAP_DIR / f"{stem}.pdf").write_bytes(rulebook_pdf(doc, ledger_ok=_ledger_ok()))
        except Exception:
            pass  # the signed JSON is already saved; the PDF is a convenience copy
        return {"version": v, "file": stem}
    except Exception:
        return None


@router.get("/versions/{version}/export")
def export_version(version: str, format: str = Query("json", pattern="^(json|csv|md|pdf)$")) -> Response:
    doc = build_doc(version)
    name = f"fraudarena-rulebook-{version}"
    if format == "csv":
        return Response(rb.to_csv(doc), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}.csv"'})
    if format == "md":
        return Response(rb.to_markdown(doc), media_type="text/markdown", headers={"Content-Disposition": f'attachment; filename="{name}.md"'})
    if format == "pdf":
        return Response(rulebook_pdf(doc, ledger_ok=_ledger_ok()), media_type="application/pdf",
                        headers={"Content-Disposition": f'attachment; filename="{name}.pdf"'})
    return JSONResponse(doc, headers={"Content-Disposition": f'attachment; filename="{name}.json"'})


@router.get("/snapshots")
def list_snapshots() -> list[dict]:
    SNAP_DIR = _snap_dir()
    if not SNAP_DIR.exists():
        return []
    return [{"name": p.name, "bytes": p.stat().st_size} for p in sorted(SNAP_DIR.glob("rulebook-*"), reverse=True)][:50]


@router.get("/snapshots/{name}")
def get_snapshot(name: str) -> Response:
    p = _snap_dir() / Path(name).name
    if not p.exists() or not p.name.startswith("rulebook-"):
        raise HTTPException(status_code=404, detail="snapshot not found")
    kind = "application/pdf" if p.suffix == ".pdf" else "application/json"
    return Response(p.read_bytes(), media_type=kind, headers={"Content-Disposition": f'attachment; filename="{p.name}"'})


@router.post("/rulebook/verify")
def verify_rulebook(doc: dict = Body(...)) -> dict:
    return {**rb.check(doc), "format": doc.get("format"), "version": doc.get("version"), "rules": len(doc.get("rules") or doc.get("plans") or [])}


def _replay_plan_for_import() -> Plan | None:
    """A known attack that still gets money through the active rules (G2/G4 need one to test against)."""
    from fa.plans.executor import execute
    from fa.verify import regression
    from fa.verify.shadow import fresh_state

    active = default_store().get(default_store().active_version())
    for p in regression.all():
        if execute(p, fresh_state({}), active).loss_through > 0:
            return p
    return None


@router.post("/rulebook/import")
def import_rulebook(doc: dict = Body(...), maker: str = Query(..., min_length=1)) -> dict:
    """Turn the rules of a rulebook file into PROPOSED patches (never live). The importer is recorded as the
    'starter', so they cannot approve their own import."""
    from fa.release.versions import propose, verify_patch

    chk = rb.check(doc)
    if chk["reason"].startswith("content was modified"):
        raise HTTPException(status_code=400, detail=chk["reason"])
    try:
        rules = rb.parse_rules(doc)
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"invalid rulebook: {str(exc).splitlines()[0]}")

    store = default_store()
    active_ids = {r.id for r in store.get(store.active_version()).rules}
    plan = _replay_plan_for_import()
    ctx: dict[str, Any] | None = None
    if plan is not None:
        from fa.config import load_config
        from fa.world.generator import build_world
        ctx = {"plan": plan, "base_rule_set": store.get(store.active_version()),
               "world": build_world(load_config().section("common").get("seed", 42))}

    results = []
    for r in rules:
        rid = r.id if r.id not in active_ids else f"IMP-{r.id}"
        rule = r.model_copy(update={"id": rid, "source": "imported"})
        pid = propose(rule, f"import:{doc.get('version', '?')}", starter=maker, ctx=ctx, store=store)
        results.append({"patch_id": pid, "rule_id": rid, "state": store.get_patch(pid)["state"]})
    note = ("Proposals checked by gates G1-G6; approve or reject them on the Story page." if ctx is not None else
            "No known attack currently gets through, so there is nothing to test the rules against yet. "
            "Proposals stay PROPOSED: run a round first, then verify.")
    return {"provenance": chk, "proposals": results, "note": note}


# ---------------------------------------------------------------- attack library

_ATTACK_LABEL = {"P1": "Account takeover and drain", "P2": "Mule chain", "P3": "Structuring below a limit"}
_replay_cache: dict[tuple[str, str], int] = {}


def _plain(plan: Plan) -> str:
    acts = [s.act.replace("_", " ") for s in plan.steps]
    moved = sum((s.amount or 0) for s in plan.steps if s.act in ("payment", "pay"))
    head = ", ".join(dict.fromkeys(acts))
    return f"{len(plan.steps)} steps ({head}); about Rs {moved // 100:,} moved in payments."


def _loss_now(plan: Plan, version: str, rs) -> int:
    key = (version, plan.plan_id)
    if key not in _replay_cache:
        from fa.plans.executor import execute
        from fa.verify.shadow import fresh_state
        _replay_cache[key] = int(execute(plan, fresh_state({}), rs).loss_through)
    return _replay_cache[key]


@router.get("/attacks")
def list_attacks() -> list[dict]:
    from fa.verify import regression

    store = default_store()
    v = store.active_version()
    rs = store.get(v)
    out = []
    for p in regression.all():
        loss = _loss_now(p, v, rs)
        out.append({"plan_id": p.plan_id, "playbook": p.playbook, "label": _ATTACK_LABEL.get(p.playbook, p.playbook),
                    "summary": _plain(p), "steps": len(p.steps), "seed": p.seed, "loss_now": loss, "stopped": loss == 0,
                    "version": v})
    return out


@router.post("/attacks/{plan_id}/replay")
def replay_attack(plan_id: str) -> dict:
    from fa.plans.executor import execute
    from fa.verify import regression
    from fa.verify.shadow import fresh_state

    plan = next((p for p in regression.all() if p.plan_id == plan_id), None)
    if plan is None:
        raise HTTPException(status_code=404, detail="attack not found")
    store = default_store()
    v = store.active_version()
    trace = execute(plan, fresh_state({}), store.get(v))
    _replay_cache[(v, plan_id)] = int(trace.loss_through)
    return {"plan_id": plan_id, "version": v, "loss_through": int(trace.loss_through), "stopped": trace.loss_through == 0,
            "decisions": [d.decision for (_s, _f, d) in trace.steps]}


@router.get("/attacks/export")
def export_attacks() -> JSONResponse:
    from fa.verify import regression

    doc = rb.seal({"format": rb.ATTACKS_FORMAT, "exported_at": time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()),
                   "data_source": _data_source(), "plans": [p.model_dump(mode="json") for p in regression.all()]})
    return JSONResponse(doc, headers={"Content-Disposition": 'attachment; filename="fraudarena-attacks.json"'})


@router.post("/attacks/import")
def import_attacks(doc: dict = Body(...)) -> dict:
    """Add attack plans to the regression set. Each plan must validate and replay without error."""
    from fa.plans.executor import execute
    from fa.verify import regression
    from fa.verify.shadow import fresh_state

    chk = rb.check(doc)
    if chk["reason"].startswith("content was modified"):
        raise HTTPException(status_code=400, detail=chk["reason"])
    if doc.get("format") != rb.ATTACKS_FORMAT or not isinstance(doc.get("plans"), list):
        raise HTTPException(status_code=400, detail=f"expected format {rb.ATTACKS_FORMAT} with a plans list")
    if len(doc["plans"]) > 200:
        raise HTTPException(status_code=400, detail="too many plans (max 200)")
    store = default_store()
    rs = store.get(store.active_version())
    added, skipped, rejected = [], [], []
    for raw in doc["plans"]:
        try:
            plan = Plan.model_validate(raw)
            execute(plan, fresh_state({}), rs)          # must at least run against the sandbox
        except Exception as exc:  # noqa: BLE001
            rejected.append({"plan_id": (raw or {}).get("plan_id") if isinstance(raw, dict) else None,
                             "reason": str(exc).splitlines()[0][:160]})
            continue
        (added if regression.add(plan) else skipped).append(plan.plan_id)
    _replay_cache.clear()
    return {"provenance": chk, "added": added, "already_present": skipped, "rejected": rejected}


# ---------------------------------------------------------------- held-out stress test

import threading

_stress: dict[str, dict] = {}
_stress_running: set[str] = set()
_stress_lock = threading.Lock()


def _run_stress(version: str) -> None:
    try:
        from fa.stress import stress_test
        _stress[version] = stress_test(default_store().get(version))
    except Exception as exc:  # noqa: BLE001
        _stress[version] = {"error": str(exc)[:200], "version": version}
    finally:
        with _stress_lock:
            _stress_running.discard(version)


@router.get("/stress")
def stress_status(run: bool = False) -> dict:
    """Result of the held-out stress test for the active version. Starts it in the background the first
    time (or with ?run=true to repeat); `status` is running | done | error."""
    v = default_store().active_version()
    with _stress_lock:
        if (v not in _stress or run) and v not in _stress_running:
            _stress_running.add(v)
            threading.Thread(target=_run_stress, args=(v,), daemon=True).start()
        running = v in _stress_running
    res = _stress.get(v)
    if running and (res is None or run):
        return {"status": "running", "version": v, "previous": res if res and "error" not in res else None}
    if res and "error" in res:
        return {"status": "error", "version": v, "error": res["error"]}
    return {"status": "done", "version": v, **(res or {})}
