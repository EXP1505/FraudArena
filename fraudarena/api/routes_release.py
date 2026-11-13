"""Owner: M4. POST /api/patches/{id}/approve, /reject, POST /api/rollback."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.post("/patches/{patch_id}/approve")
def approve_patch(patch_id: str, checker: str) -> dict:
    raise NotImplementedError


@router.post("/patches/{patch_id}/reject")
def reject_patch(patch_id: str, checker: str, reason: str) -> dict:
    raise NotImplementedError


@router.post("/rollback")
def rollback(to_version: str, checker: str) -> dict:
    raise NotImplementedError
