"""Owner: M2. Data fidelity: how close the simulated world is to the RBIH data (fa/world/fidelity.py).

GET  /api/fidelity               report (computed in the background the first time, then cached)
GET  /api/fidelity/export        signed JSON certificate (PDF with ?format=pdf)
POST /api/fidelity/calibrate     start a calibration suggestion (nothing is changed on disk)
GET  /api/fidelity/calibrate     status / result of that suggestion
"""
from __future__ import annotations

import threading
import time

from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import JSONResponse, Response

from fa.release import rulebook as rb

router = APIRouter(prefix="/api/fidelity")

_state: dict = {"report": None, "running": False, "error": None, "at": None}
_cal: dict = {"result": None, "running": False, "error": None}
_lock = threading.Lock()


def _compute() -> None:
    try:
        from fa.world.fidelity import report
        res = report()
        _state.update(report=res, error=None, at=time.strftime("%Y-%m-%d %H:%M:%S UTC", time.gmtime()))
    except Exception as exc:  # noqa: BLE001
        _state["error"] = str(exc)[:200]
    finally:
        with _lock:
            _state["running"] = False


def _start(force: bool = False) -> None:
    with _lock:
        if _state["running"] or (_state["report"] is not None and not force):
            return
        _state["running"] = True
    threading.Thread(target=_compute, daemon=True).start()


@router.get("")
def get_fidelity(refresh: bool = False) -> dict:
    _start(force=refresh)
    if _state["report"] is None:
        if _state["error"] and not _state["running"]:
            return {"status": "error", "error": _state["error"]}
        return {"status": "running"}
    return {"status": "running" if _state["running"] else "done", "at": _state["at"], **_state["report"]}


def _certificate() -> dict:
    if _state["report"] is None:
        raise HTTPException(status_code=409, detail="report not ready yet: open the Data page first")
    from api.routes_export import _data_source
    cal = _cal["result"]
    return rb.seal({"format": "fraudarena.fidelity/1", "computed_at": _state["at"], "data_source": _data_source(),
                    "report": _state["report"], "calibration_suggestion": cal if cal and cal.get("available") else None})


@router.get("/export")
def export_fidelity(format: str = Query("json", pattern="^(json|pdf)$")) -> Response:
    doc = _certificate()
    if format == "pdf":
        try:
            from api.report import fidelity_pdf
        except ImportError as exc:
            raise HTTPException(status_code=503, detail="PDF export needs reportlab: pip install reportlab") from exc
        return Response(fidelity_pdf(doc), media_type="application/pdf",
                        headers={"Content-Disposition": 'attachment; filename="fraudarena-data-fidelity.pdf"'})
    return JSONResponse(doc, headers={"Content-Disposition": 'attachment; filename="fraudarena-data-fidelity.json"'})


def _run_cal() -> None:
    try:
        from fa.world.fidelity import suggest_calibration
        _cal.update(result=suggest_calibration(), error=None)
    except Exception as exc:  # noqa: BLE001
        _cal["error"] = str(exc)[:200]
    finally:
        with _lock:
            _cal["running"] = False


@router.post("/calibrate")
def start_calibration() -> dict:
    with _lock:
        if not _cal["running"]:
            _cal.update(running=True, result=None, error=None)
            threading.Thread(target=_run_cal, daemon=True).start()
    return {"status": "running"}


@router.get("/calibrate")
def calibration_status() -> dict:
    if _cal["running"]:
        return {"status": "running"}
    if _cal["error"]:
        return {"status": "error", "error": _cal["error"]}
    if _cal["result"] is None:
        return {"status": "idle"}
    return {"status": "done", **_cal["result"]}
