"""Owner: M2. POST /api/rounds, GET /api/rounds/{id}, GET /api/versions,
GET /api/versions/{v}, GET /api/metrics, POST /api/world/reset.
"""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api")


@router.post("/rounds")
def post_round(playbook: str) -> dict:
    raise NotImplementedError


@router.get("/rounds/{round_id}")
def get_round(round_id: str) -> dict:
    raise NotImplementedError


@router.get("/versions")
def list_versions() -> list[dict]:
    raise NotImplementedError


@router.get("/versions/{version}")
def get_version(version: str) -> dict:
    raise NotImplementedError


@router.get("/metrics")
def get_metrics() -> dict:
    raise NotImplementedError


@router.post("/world/reset")
def reset_world() -> dict:
    raise NotImplementedError
