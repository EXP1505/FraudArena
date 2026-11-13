"""Owner: M2. GET /api/ledger, GET /api/ledger/verify, POST /api/ledger/tamper-demo
(operates on a scratch copy; the real ledger table is never touched)."""
from __future__ import annotations

from fastapi import APIRouter

router = APIRouter(prefix="/api/ledger")


@router.get("")
def list_ledger() -> list[dict]:
    raise NotImplementedError


@router.get("/verify")
def verify_ledger() -> dict:
    raise NotImplementedError


@router.post("/tamper-demo")
def tamper_demo() -> dict:
    raise NotImplementedError
