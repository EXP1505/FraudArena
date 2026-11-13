"""Owner: M4. POST /api/patches/{id}/approve, /reject, POST /api/rollback; GET /api/patches."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException

from fa.release import approve as approve_mod
from fa.release import rollback as rollback_mod
from fa.release.versions import ReleaseError, default_store

router = APIRouter(prefix="/api")


def _run(fn, *args, **kwargs) -> dict:
    try:
        return fn(*args, **kwargs)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc).strip("'\"")) from exc
    except ReleaseError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.get("/patches")
def list_patches() -> list[dict]:
    return default_store().list_patches()


@router.get("/patches/{patch_id}")
def get_patch(patch_id: str) -> dict:
    return _run(default_store().get_patch, patch_id)


@router.post("/patches/{patch_id}/approve")
def approve_patch(patch_id: str, checker: str) -> dict:
    return _run(approve_mod.approve, patch_id, checker)


@router.post("/patches/{patch_id}/reject")
def reject_patch(patch_id: str, checker: str, reason: str = "") -> dict:
    return _run(approve_mod.reject, patch_id, checker, reason)


@router.post("/rollback")
def rollback(to_version: str, checker: str) -> dict:
    return _run(rollback_mod.rollback, to_version, checker)
