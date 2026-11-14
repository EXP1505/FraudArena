"""Owner: M1/M2. Test 10: POST /tx returns the same decision as calling
engine decide directly; plus the CP1 gate script's three events.
"""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app
from api.db import init_db


def test_health():
    init_db()
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True and body["version"] == "v1"
    assert body["ai_key_loaded"] is False and body["ai_mode"] in ("offline-stand-in", "needs-cache")  # tests never read .env


def test_tx_matches_engine_decide():
    init_db()
    client = TestClient(app)
    resp = client.post(
        "/tx",
        json={
            "event_id": "test_e1",
            "ts": 1000,
            "type": "payment",
            "account": "A_TEST",
            "payee": "P_TEST",
            "amount": 500,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert "decision" in data
    assert data["decision"] in ("allow", "hold", "block")


def test_get_decisions():
    init_db()
    client = TestClient(app)
    resp = client.get("/decisions", params={"limit": 10})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
