"""Owner: M4. Before the first round nothing is measured: the dashboard starts blank and fills in from real runs."""
from __future__ import annotations

from fastapi.testclient import TestClient

from api import routes_export, routes_rounds
from api.db import init_db
from api.main import app


def _client():
    init_db()
    return TestClient(app)


def test_metrics_are_empty_and_nothing_is_measured_until_a_round_exists(monkeypatch):
    started = []
    monkeypatch.setattr(routes_rounds, "db_list_rounds", lambda: [])
    monkeypatch.setattr(routes_rounds.threading, "Thread", lambda *a, **k: started.append(1))
    j = _client().get("/api/metrics").json()
    assert j["waiting_for_first_round"] is True and j["measured"] is False and j["measuring"] is False
    assert j["history"] == [] and all(v is None for v in j["summary"].values())
    assert started == []                                           # no background measurement was started


def test_metrics_start_measuring_once_a_round_exists(monkeypatch):
    started = []

    class Fake:
        def __init__(self, *a, **k): pass
        def start(self): started.append(1)

    monkeypatch.setattr(routes_rounds, "db_list_rounds", lambda: [{"id": "r"}])
    monkeypatch.setattr(routes_rounds, "get_metrics_records", lambda: [])
    monkeypatch.setattr(routes_rounds, "_measuring", set())
    monkeypatch.setattr(routes_rounds.threading, "Thread", Fake)
    j = _client().get("/api/metrics").json()
    assert "waiting_for_first_round" not in j and started == [1] and j["measuring"] is True


def test_stress_test_waits_for_the_first_round(monkeypatch):
    import api.db as db
    started = []
    monkeypatch.setattr(db, "list_rounds", lambda: [])
    monkeypatch.setattr(routes_export, "_stress", {})
    monkeypatch.setattr(routes_export.threading, "Thread", lambda *a, **k: started.append(1))
    assert _client().get("/api/stress").json()["status"] == "waiting" and started == []


def _jobs_for(monkeypatch, rounds, records):
    seen = {}

    class Fake:
        def __init__(self, target=None, args=(), **k): seen["args"] = args
        def start(self): pass

    monkeypatch.setattr(routes_rounds, "db_list_rounds", lambda: rounds)
    monkeypatch.setattr(routes_rounds, "get_metrics_records", lambda: records)
    monkeypatch.setattr(routes_rounds, "_measuring", set())
    monkeypatch.setattr(routes_rounds.threading, "Thread", Fake)
    j = _client().get("/api/metrics").json()
    return j, (seen["args"][0] if seen else None)


def _row(v, pb):
    return {"version": v, "playbook": pb, "wcel": 100, "hold_rate": 0.01, "hold_rate_lo": 0.008, "hold_rate_hi": 0.012,
            "detection_delay_s": 0, "recorded_at": "x"}


def test_only_the_attack_types_that_were_run_are_measured(monkeypatch):
    j, jobs = _jobs_for(monkeypatch, [{"id": "r1", "playbook": "P1"}], [])
    assert j["played"] == ["P1"] and jobs == {"v1": ["P1"]}               # P2 and P3 are not touched


def test_running_another_attack_type_later_measures_just_that_one(monkeypatch):
    j, jobs = _jobs_for(monkeypatch, [{"id": "r1", "playbook": "P1"}, {"id": "r2", "playbook": "P3"}], [_row("v1", "P1")])
    assert j["played"] == ["P1", "P3"] and jobs == {"v1": ["P3"]}
    assert j["measured"] is False                                       # P3 has no row yet, so the page keeps saying "measuring"
    assert j["summary"]["wcel_p2"] is None and j["summary"]["wcel_p3"] is None


def test_ai_only_rounds_measure_friction_but_no_built_in_attack(monkeypatch):
    j, jobs = _jobs_for(monkeypatch, [{"id": "r1", "playbook": "X-abc12345"}], [])
    assert j["played"] == [] and jobs == {"v1": []}
    j, jobs = _jobs_for(monkeypatch, [{"id": "r1", "playbook": "X-abc12345"}], [_row("v1", "_friction")])
    assert jobs is None and j["measured"] is True and j["summary"]["hold_rate_pct"] == 1.0


def test_measured_is_false_until_every_played_attack_type_has_a_row(monkeypatch):
    j, _ = _jobs_for(monkeypatch, [{"id": "r1", "playbook": "P1"}, {"id": "r2", "playbook": "P2"}], [_row("v1", "P1")])
    assert j["measured"] is False
