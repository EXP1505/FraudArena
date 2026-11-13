"""Owner: M2. append(action, payload) -> LedgerRecord.

hash = SHA256(canonical_json(record minus hash and sig) + prev_hash); the
genesis record's prev_hash is 64 zeros.
"""
from __future__ import annotations

from fa.contracts import LedgerRecord

GENESIS_PREV_HASH = "0" * 64


def append(action: str, payload: dict) -> LedgerRecord:
    raise NotImplementedError
