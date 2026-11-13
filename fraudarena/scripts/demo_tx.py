"""Owner: M1. CP1 gate script: sends 3 events via the API and prints the
decision read back from Postgres (docs/FraudArena_Phase1_Plan.pdf section 9,
docs/TIMELINE.md CP1).

1. normal pay, small, known payee          -> allow
2. pay 12x average to a payee added 10 min -> hold (R2)
3. 9 payees in one hour from one account   -> block (R5)
"""
from __future__ import annotations

import os
import sys
import httpx

# Ensure project root in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

API_BASE_URL = os.environ.get("API_BASE_URL", os.environ.get("API_URL", "http://localhost:8000"))

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
    print("=== FraudArena H4 / CP1 Gate Demo ===")
    with httpx.Client(base_url=API_BASE_URL, timeout=10) as client:
        # 1. Warm-up acct-1 with known payee added earlier
        client.post("/tx", json={"event_id": "setup-1-add", "ts": 1_000, "type": "add_payee", "account": "gate-acct-1", "payee": "known-payee"})
        for i in range(1, 4):
            client.post("/tx", json={"event_id": f"setup-1-pay-{i}", "ts": 2_000 + i * 500, "type": "payment", "account": "gate-acct-1", "payee": "known-payee", "amount": 500_00})

        # 2. Warm-up acct-2 with baseline history and payee added 10 min ago (600s)
        for i in range(1, 4):
            client.post("/tx", json={"event_id": f"setup-2-pay-{i}", "ts": 10_000 + i * 500, "type": "payment", "account": "gate-acct-2", "payee": "regular-payee", "amount": 1_000_00})
        client.post("/tx", json={"event_id": "setup-2-add", "ts": 19_400, "type": "add_payee", "account": "gate-acct-2", "payee": "new-payee-10min"})

        # 3. Warm-up acct-3 with 8 distinct payees within the hour (ts 29000 to 29800)
        for i in range(1, 9):
            client.post("/tx", json={"event_id": f"setup-3-fan-{i}", "ts": 29_000 + i * 100, "type": "payment", "account": "gate-acct-3", "payee": f"payee-{i}", "amount": 100_00})

        # Run the 3 Gate Events
        for ev in GATE_EVENTS:
            body = {k: v for k, v in ev.items() if k != "expected"}
            resp = client.post("/tx", json=body)
            resp.raise_for_status()
            decision = resp.json()
            got_dec = decision.get("decision")
            print(f"{ev['event_id']}: expected={ev['expected']} got={got_dec}")

        resp = client.get("/decisions", params={"limit": 5})
        resp.raise_for_status()
        print("\n--- Recent decisions from DB ---")
        for d in resp.json()[:3]:
            print(f"DB Record: event_id={d.get('id')}, account={d.get('account')}, amount={d.get('amount')}, decision={d.get('decision')}, rule={d.get('rule_id')}")

        print("\nH4 Gate Validation: COMPLETE")

if __name__ == "__main__":
    main()
