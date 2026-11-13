"""Owner: M2. append(action, payload) -> LedgerRecord.

hash = SHA256(canonical_json(record minus hash and sig) + prev_hash); the
genesis record's prev_hash is 64 zeros.
"""
from __future__ import annotations

import hashlib
import json
import time

from api.db import append_ledger_record, get_last_ledger_record
from fa.contracts import LedgerRecord
from fa.ledger.sign import sign

GENESIS_PREV_HASH = "0" * 64


def append(action: str, payload: dict, table: str = "ledger") -> LedgerRecord:
    """Append a new action and payload to the tamper-evident hash chain."""
    last = get_last_ledger_record(table=table)
    if last is None:
        prev_hash = GENESIS_PREV_HASH
        seq = 1
    else:
        prev_hash = last["hash"]
        seq = last["seq"] + 1

    ts = int(time.time())
    record_dict = {
        "action": action,
        "payload": payload,
        "seq": seq,
        "ts": ts,
    }
    canonical = json.dumps(record_dict, sort_keys=True, separators=(",", ":"))
    hash_val = hashlib.sha256((canonical + prev_hash).encode("utf-8")).hexdigest()
    sig = sign(hash_val.encode("utf-8"))

    inserted_seq = append_ledger_record(ts, action, payload, prev_hash, hash_val, sig, table=table)

    return LedgerRecord(
        seq=inserted_seq or seq,
        ts=ts,
        action=action,
        payload=payload,
        prev_hash=prev_hash,
        hash=hash_val,
        sig=sig,
    )
