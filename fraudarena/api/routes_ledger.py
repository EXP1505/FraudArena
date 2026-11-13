"""Owner: M2. GET /api/ledger, GET /api/ledger/verify, POST /api/ledger/tamper-demo
(operates on a scratch copy; the real ledger table is never touched)."""
from __future__ import annotations

from fastapi import APIRouter

from api.db import (
    create_scratch_ledger,
    drop_scratch_ledger,
    get_ledger_records,
    tamper_scratch_ledger,
)
from fa.ledger.verify import verify

router = APIRouter(prefix="/api/ledger")


@router.get("")
def list_ledger() -> list[dict]:
    """Retrieve all records from the real ledger table."""
    return get_ledger_records(table="ledger")


@router.get("/verify")
def verify_ledger() -> dict:
    """Verify integrity of the real ledger chain."""
    broken_seq = verify(table="ledger")
    return {
        "ok": broken_seq is None,
        "broken_seq": broken_seq,
        "status": "valid" if broken_seq is None else f"tampered at seq {broken_seq}",
    }


@router.post("/tamper-demo")
def tamper_demo() -> dict:
    """Tamper-evidence demo: copies real ledger to scratch, tampers one row,
    runs verify(), and returns the detected broken sequence."""
    scratch = "scratch_demo_ledger"
    create_scratch_ledger(scratch_table=scratch)
    try:
        tampered_seq = tamper_scratch_ledger(scratch_table=scratch)
        detected_seq = verify(table=scratch)
        return {
            "demo": "tamper_detected",
            "tampered_seq": tampered_seq,
            "detected_at_seq": detected_seq,
            "success": detected_seq == tampered_seq,
            "detail": f"Cryptographic mismatch detected at block #{detected_seq}",
        }
    finally:
        drop_scratch_ledger(scratch_table=scratch)
