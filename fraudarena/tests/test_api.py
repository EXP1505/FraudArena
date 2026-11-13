# Owner: M1/M2. API test: test 10 of Phase 1
import os
import sys
import pytest

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

from api.db import init_db, get_active_rule_version, get_rules_for_version, get_decisions
from api.main import process_transaction
from fa.contracts import Event

def test_health_and_db_init():
    init_db()
    version = get_active_rule_version()
    assert version >= 1
    rules = get_rules_for_version(version)
    assert rules is not None
    assert len(rules) >= 5

def test_api_tx_returns_decision_and_persists():
    init_db()
    run_id = "test_run_api_10"
    event = Event(
        id="test_ev_01",
        ts=700000,
        account="A-TEST-1",
        type="pay",
        amount=500.0,
        payee="P-REGULAR"
    )
    decision = process_transaction(event, run_id=run_id)
    assert decision.event_id == "test_ev_01"
    assert decision.action in ("allow", "hold", "block")
    assert "amount_ratio_30d" in decision.features

    # Verify recorded in DB
    recs = get_decisions(run_id=run_id, limit=1)
    assert len(recs) == 1
    assert recs[0]["account"] == "A-TEST-1"
    assert recs[0]["action"] == decision.action

def test_h4_demo_scenarios():
    init_db()
    run_id = "test_h4_scenarios"
    
    # 1. Normal
    d1 = process_transaction(Event(
        id="demo_t1", ts=800000, account="A-H4-1", type="pay", amount=200, payee="P1"
    ), run_id=run_id)
    assert d1.action == "allow"

    # 2. Large to new payee (12x average, age 10m)
    process_transaction(Event(id="setup_t2", ts=810000, account="A-H4-2", type="payee_add", payee="P-NEW"), run_id=run_id)
    d2 = process_transaction(Event(id="demo_t2", ts=810600, account="A-H4-2", type="pay", amount=120000, payee="P-NEW"), run_id=run_id)
    assert d2.action == "hold"
    assert d2.rule_id == "R2"

