"""Owner: M2. Tamper test: editing one field in a stored ledger row must be
caught by fa.ledger.verify.verify() at that row's seq.
"""
from __future__ import annotations

from api.db import (
    create_scratch_ledger,
    drop_scratch_ledger,
    init_db,
    tamper_scratch_ledger,
)
from fa.ledger import chain, verify


def test_tamper_detected_at_edited_row():
    init_db()

    # Append 3 real records to ledger
    r1 = chain.append("test_action_1", {"amount": 1000, "user": "alice"})
    r2 = chain.append("test_action_2", {"amount": 2500, "user": "bob"})
    r3 = chain.append("test_action_3", {"amount": 5000, "user": "carol"})

    assert r2.seq == r1.seq + 1
    assert r3.seq == r2.seq + 1

    # 1. Unaltered ledger verifies cleanly
    assert verify.verify("ledger") is None

    # 2. Copy to scratch table for isolated tamper test
    scratch_table = "test_scratch_ledger"
    create_scratch_ledger(scratch_table=scratch_table)
    try:
        # Scratch table is initially valid
        assert verify.verify(scratch_table) is None

        # Tamper with row r2 in scratch table
        tampered_seq = tamper_scratch_ledger(seq=r2.seq, scratch_table=scratch_table)
        assert tampered_seq == r2.seq

        # Verification must catch the tamper at seq r2.seq
        broken = verify.verify(scratch_table)
        assert broken == r2.seq, f"Expected broken seq {r2.seq}, but got {broken}"
    finally:
        drop_scratch_ledger(scratch_table=scratch_table)
