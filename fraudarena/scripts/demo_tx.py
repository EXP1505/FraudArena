# Owner: M1/M2. Prints allow, hold, block for the three H4 gate events, read back from the database.
import os
import sys
import time
import requests

# Ensure project root is in sys.path
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.db import init_db, get_decisions, get_active_rule_version
from api.main import process_transaction
from fa.contracts import Event

API_URL = os.getenv("API_URL", "http://localhost:8000")

def is_api_online():
    try:
        r = requests.get(f"{API_URL}/health", timeout=1.0)
        return r.status_code == 200
    except Exception:
        return False

def send_tx(event_dict, run_id="demo_gate_h4"):
    if is_api_online():
        resp = requests.post(f"{API_URL}/tx?run_id={run_id}", json=event_dict)
        return resp.json()
    else:
        # Direct execution fallback
        ev = Event(**event_dict)
        dec = process_transaction(ev, run_id=run_id)
        return dec.model_dump()

def main():
    print("=== FraudArena H4 Gate Demo ===")
    init_db()
    run_id = f"gate_run_{int(time.time())}"

    # 1. Setup base state: Known payee added 5 days ago (432,000s)
    send_tx({
        "id": "e_setup_1",
        "ts": 1000,
        "account": "A-101",
        "type": "payee_add",
        "payee": "P-KNOWN"
    }, run_id=run_id)

    # 1. Normal payment: small amount to known payee
    tx1 = send_tx({
        "id": "e_demo_1",
        "ts": 433000,
        "account": "A-101",
        "type": "pay",
        "amount": 500,
        "payee": "P-KNOWN"
    }, run_id=run_id)
    print(f"1. Normal payment: {tx1.get('action')} (expected: allow)")

    # 2. Payee added 10 minutes (600s) ago, then payment 12x average (120,000 paise)
    send_tx({
        "id": "e_setup_2",
        "ts": 500000,
        "account": "A-102",
        "type": "payee_add",
        "payee": "P-NEW"
    }, run_id=run_id)

    tx2 = send_tx({
        "id": "e_demo_2",
        "ts": 500600,
        "account": "A-102",
        "type": "pay",
        "amount": 120000,
        "payee": "P-NEW"
    }, run_id=run_id)
    print(f"2. Pay 12x average to payee added 10 min: {tx2.get('action')} ({tx2.get('rule_id')}) (expected: hold (R2))")

    # 3. Rapid fan-out: 9 payees in 1 hour from one account
    send_tx({
        "id": "e_setup_3",
        "ts": 600000,
        "account": "A-103",
        "type": "device_add",
        "device": "D-103"
    }, run_id=run_id)

    for i in range(1, 9):
        send_tx({
            "id": f"e_fan_warmup_{i}",
            "ts": 600000 + i * 100,
            "account": "A-103",
            "type": "pay",
            "amount": 1000,
            "payee": f"P-FAN-{i}"
        }, run_id=run_id)

    tx3 = send_tx({
        "id": "e_demo_3",
        "ts": 601000,
        "account": "A-103",
        "type": "pay",
        "amount": 1000,
        "payee": "P-FAN-9"
    }, run_id=run_id)
    print(f"3. 9 payees in 1 hour from one account: {tx3.get('action')} ({tx3.get('rule_id')}) (expected: block (R5))")

    # Verify directly from database
    print("\n--- Verifying from Database (Events Table) ---")
    if is_api_online():
        resp = requests.get(f"{API_URL}/decisions?run_id={run_id}&limit=3")
        recent = resp.json()
    else:
        recent = get_decisions(run_id=run_id, limit=3)

    for r in reversed(recent):
        print(f"DB Record: event_id={r['id']}, account={r['account']}, amount={r['amount']}, action={r['action']}, rule={r['rule_id']}")

    print("\nH4 Gate Validation: COMPLETE")

if __name__ == "__main__":
    main()
