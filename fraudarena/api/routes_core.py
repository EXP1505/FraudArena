"""Owner: M2. GET /health, POST /tx, GET /decisions."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter()

RULE_VERSION = "v1"


@router.get("/health")
def health() -> dict:
    return {"ok": True, "version": RULE_VERSION}


@router.post("/tx")
def post_tx(event: dict) -> dict:
    raise NotImplementedError


@router.get("/decisions")
def get_decisions(run_id: str | None = None, limit: int = 100) -> list[dict]:
    raise NotImplementedError
