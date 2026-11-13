"""Owner: M2. verify(table="ledger") -> int | None; first broken seq, or
None if the whole chain verifies.
"""
from __future__ import annotations

import hashlib
import json

from api.db import get_ledger_records
from fa.ledger.chain import GENESIS_PREV_HASH
from fa.ledger.sign import verify_signature


def verify(table: str = "ledger") -> int | None:
    """Verify the integrity of the ledger hash chain and Ed25519 signatures.

    Returns:
        None if every block is valid, or the `seq` number of the first broken row.
    """
    records = get_ledger_records(table=table)
    if not records:
        return None

    expected_prev_hash = GENESIS_PREV_HASH
    expected_seq = 1

    for row in records:
        seq = row["seq"]
        ts = row["ts"]
        action = row["action"]
        payload = row["payload"]
        prev_hash = row["prev_hash"]
        hash_val = row["hash"]
        sig = row["sig"]

        # 1. Monotonic sequence check
        if seq != expected_seq:
            return seq

        # 2. Previous hash link check
        if prev_hash != expected_prev_hash:
            return seq

        # 3. Hash computation check
        record_dict = {
            "action": action,
            "payload": payload,
            "seq": seq,
            "ts": ts,
        }
        canonical = json.dumps(record_dict, sort_keys=True, separators=(",", ":"))
        expected_hash = hashlib.sha256((canonical + prev_hash).encode("utf-8")).hexdigest()
        if hash_val != expected_hash:
            return seq

        # 4. Digital signature check
        if not verify_signature(hash_val.encode("utf-8"), sig):
            return seq

        expected_prev_hash = hash_val
        expected_seq = seq + 1

    return None
