"""Owner: M1. CP1 gate script: sends 3 events via the API and prints the
decision read back from Postgres (docs/FraudArena_Phase1_Plan.pdf section 9,
docs/TIMELINE.md CP1).

1. normal pay, small, known payee          -> allow
2. pay 12x average to a payee added 10 min -> hold (R2)
3. 9 payees in one hour from one account   -> block (R5)

Coded against M2's POST /tx and GET /decisions endpoints, which are still
stubs -- this will raise once it reaches the API until those land.
"""
from __future__ import annotations

import os

import httpx

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")

GATE_EVENTS = [
    {
        "event_id": "gate-1-normal-pay",
        "ts": 10_000,
        "type": "payment",
        "account": "gate-acct-1",
        "payee": "known-payee",
        "amount": 500_00,
        "expected": "allow",
    },
    {
        "event_id": "gate-2-big-new-payee",
        "ts": 20_000,
        "type": "payment",
        "account": "gate-acct-2",
        "payee": "new-payee-10min",
        "amount": 12_000_00,
        "expected": "hold",
    },
    {
        "event_id": "gate-3-fan-out",
        "ts": 30_000,
        "type": "payment",
        "account": "gate-acct-3",
        "payee": "payee-9",
        "amount": 100_00,
        "expected": "block",
    },
]


def main() -> None:
    with httpx.Client(base_url=API_BASE_URL, timeout=10) as client:
        for ev in GATE_EVENTS:
            body = {k: v for k, v in ev.items() if k != "expected"}
            resp = client.post("/tx", json=body)
            resp.raise_for_status()
            decision = resp.json()
            print(f"{ev['event_id']}: expected={ev['expected']} got={decision.get('decision')}")

        resp = client.get("/decisions", params={"limit": 10})
        resp.raise_for_status()
        print("recent decisions from DB:", resp.json())


if __name__ == "__main__":
    main()
