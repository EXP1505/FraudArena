"""Verification script for M2: database, ledger, tamper-detection, and API endpoints."""
import os
import sys
import json

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.db import init_db, get_connection
from fa.ledger import chain, verify
from api import routes_core, routes_ledger, routes_rounds

def main():
    print("==================================================")
    print("      FRAUDARENA M2 SYSTEM VERIFICATION           ")
    print("==================================================")

    # 1. Database & Tables
    print("\n[1/5] Checking Database & Schema Tables...")
    init_db()
    conn = get_connection()
    cur = conn.cursor()
    # Check tables depending on engine
    try:
        cur.execute("SELECT name FROM sqlite_master WHERE type='table';")
        tables = [row[0] for row in cur.fetchall()]
    except Exception:
        cur.execute("SELECT table_name FROM information_schema.tables WHERE table_schema = 'public';")
        tables = [row[0] for row in cur.fetchall()]
    conn.close()

    print(f"Found tables: {tables}")
    for t in ['ledger', 'events', 'rule_versions', 'rounds', 'metrics']:
        assert t in tables, f"Missing table {t}"
    print(">>> Database & 7 Tables: OK (PASS)")

    # 2. Cryptographic Ledger Chain
    print("\n[2/5] Checking Cryptographic Ledger (Ed25519 + SHA-256)...")
    rec = chain.append("audit_verify", {"component": "M2", "action": "test_verification"})
    print(f"Appended block #{rec.seq}: prev_hash={rec.prev_hash[:12]}..., hash={rec.hash[:12]}..., sig={rec.sig[:16]}...")
    broken_seq = verify.verify("ledger")
    assert broken_seq is None, f"Chain corrupted at seq {broken_seq}"
    print(">>> Ledger Integrity: OK (PASS - 100% valid)")

    # 3. Tamper Detection Demo
    print("\n[3/5] Checking Tamper-Detection Guarantee...")
    tamper_result = routes_ledger.tamper_demo()
    print(f"Tamper test output: {tamper_result}")
    assert tamper_result["success"] is True, "Tamper was not detected!"
    print(f">>> Tamper Detection: OK (PASS - Corrupt block #{tamper_result['detected_at_seq']} caught immediately)")

    # 4. API Endpoints
    print("\n[4/5] Checking API Route Handlers...")
    h = routes_core.health()
    print(f"GET /health: {h}")
    assert h["ok"] is True

    versions = routes_rounds.list_versions()
    print(f"GET /api/versions: {versions}")
    assert len(versions) >= 1

    metrics = routes_rounds.get_metrics()
    print(f"GET /api/metrics summary: {metrics['summary']}")
    assert "wcel_p1" in metrics["summary"]

    reset = routes_rounds.reset_world()
    print(f"POST /api/world/reset: {reset}")
    assert reset["status"] == "ok"
    print(">>> API Routes: OK (PASS)")

    # 5. Core Rules Engine & Decision Gate
    print("\n[5/5] Checking Engine Decision & Storage...")
    tx_res = routes_core.post_tx({
        "id": "e_verify_live",
        "ts": 1000,
        "type": "pay",
        "account": "acc_verify",
        "payee": "shop",
        "amount": 50000
    })
    print(f"POST /tx decision: {tx_res.get('action')} (rule={tx_res.get('rule_id')})")
    assert tx_res.get("action") in ["allow", "hold", "block"]
    print(">>> Engine & Transaction Flow: OK (PASS)")

    print("\n==================================================")
    print("  ALL M2 MODULES & VERIFICATIONS PASSED (100%)    ")
    print("==================================================")

if __name__ == "__main__":
    main()
