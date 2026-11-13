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


def test_reset_world_clears_run_data_but_keeps_ledger(monkeypatch, tmp_path):
    """Reset = clean slate (v1 active, no rounds/patches/v2+/regression plans); ledger history stays."""
    import json

    from api.db import get_ledger_records, list_rounds, save_round
    from fa.release.versions import VersionStore

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 't.db').as_posix()}")
    monkeypatch.setenv("FA_RULES_STORE", str(tmp_path / "rules"))
    monkeypatch.setenv("FA_REGRESSION_PATH", str(tmp_path / "reg.json"))
    init_db()
    (tmp_path / "reg.json").write_text('[{"plan_id": "x"}]')
    store = VersionStore(tmp_path / "rules")
    monkeypatch.setattr("fa.release.versions._default", store)
    from fa.verify.regression import RegressionStore
    monkeypatch.setattr("fa.verify.regression._default", RegressionStore(tmp_path / "reg.json"))
    (tmp_path / "rules" / "versions").mkdir(parents=True)
    (tmp_path / "rules" / "versions" / "v1.json").write_text(json.dumps({"version": "v1", "rules": []}))
    (tmp_path / "rules" / "versions" / "v2.json").write_text(json.dumps({"version": "v2", "rules": []}))
    (tmp_path / "rules" / "patches").mkdir()
    (tmp_path / "rules" / "patches" / "pt-1.json").write_text("{}")
    store.set_active("v2")
    for i in range(3):
        save_round(f"rnd-{i}", "P1", "t", "DONE")
    assert len(list_rounds()) == 3

    out = routes_rounds.reset_world()

    assert out["active_version"] == "v1" and store.active_version() == "v1"
    assert not (tmp_path / "rules" / "versions" / "v2.json").exists() and (tmp_path / "rules" / "versions" / "v1.json").exists()
    assert not (tmp_path / "rules" / "patches").exists()
    assert list_rounds() == []
    assert json.loads((tmp_path / "reg.json").read_text()) == []
    assert any(r["action"] == "world_reset" for r in get_ledger_records())


def test_background_round_updates_the_polled_round_id(monkeypatch, tmp_path):
    """The id returned to the browser must be the one that gets the real outcome (it used to stay RUNNING)."""
    from api.db import get_round, list_rounds

    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'r.db').as_posix()}")
    init_db()
    seen = {}

    def fake(playbook, started_by, round_id=None):
        seen["id"] = round_id
        return round_id, {"state": "NO_SAFE_PATCH", "loss_through": 1}

    monkeypatch.setattr("fa.orchestrator.run_round_detailed", fake)
    routes_rounds._background_round("rnd-test", "P1", "tester")
    assert seen["id"] == "rnd-test"
    assert get_round("rnd-test")["state"] == "NO_SAFE_PATCH"
    assert len(list_rounds()) == 1                      # no duplicate row under a different id
