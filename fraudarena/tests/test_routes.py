"""Owner: M2. Round state is queryable over the API (CP2)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from api.main import app


def test_health_ok():
    client = TestClient(app)
    resp = client.get("/health")
    assert resp.status_code == 200
    assert resp.json() == {"ok": True, "version": "v1"}
