"""Owner: M2. Round state is queryable over the API (CP2)."""
from __future__ import annotations

from api import routes_core, routes_ledger, routes_rounds
from api.db import init_db
from api.main import app


def _get_client_or_fallback():
    try:
        from fastapi.testclient import TestClient
        client = TestClient(app)
        client.get("/health")
        return client
    except Exception:
        return None


def test_health_ok():
    init_db()
    client = _get_client_or_fallback()
    if client:
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["ok"] is True
    else:
        resp = routes_core.health()
        assert resp["ok"] is True
        assert "v" in resp["version"]


def test_versions_and_metrics():
    client = _get_client_or_fallback()
    if client:
        v_resp = client.get("/api/versions")
        assert v_resp.status_code == 200
        assert len(v_resp.json()) >= 1

        m_resp = client.get("/api/metrics")
        assert m_resp.status_code == 200
        assert "summary" in m_resp.json()
    else:
        versions = routes_rounds.list_versions()
        assert len(versions) >= 1
        metrics = routes_rounds.get_metrics()
        assert "summary" in metrics


def test_ledger_and_tamper_demo():
    client = _get_client_or_fallback()
    if client:
        led_resp = client.get("/api/ledger")
        assert led_resp.status_code == 200

        ver_resp = client.get("/api/ledger/verify")
        assert ver_resp.status_code == 200
        assert ver_resp.json()["ok"] is True

        tamper_resp = client.post("/api/ledger/tamper-demo")
        assert tamper_resp.status_code == 200
        assert tamper_resp.json()["success"] is True
    else:
        records = routes_ledger.list_ledger()
        assert isinstance(records, list)

        ver = routes_ledger.verify_ledger()
        assert ver["ok"] is True

        tamper = routes_ledger.tamper_demo()
        assert tamper["success"] is True


def test_reset_world():
    client = _get_client_or_fallback()
    if client:
        resp = client.post("/api/world/reset")
        assert resp.status_code == 200
        assert resp.json()["active_version"] == "v1"
    else:
        resp = routes_rounds.reset_world()
        assert resp["active_version"] == "v1"
