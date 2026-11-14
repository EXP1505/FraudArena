"""Owner: M4. Credits: 200 each, spent on compute, never on safety actions."""
from __future__ import annotations

import time

import pytest
from fastapi.testclient import TestClient

from api import auth, autopilot, credits, routes_rounds
from api.db import get_round, init_db, save_round
from api.main import app


@pytest.fixture
def client(monkeypatch, tmp_path):
    init_db()
    monkeypatch.setenv("FA_CREDITS_PATH", str(tmp_path / "credits.json"))
    monkeypatch.setenv("FA_AUTH_SECRET_PATH", str(tmp_path / "secret"))
    for k in ("GOOGLE_CLIENT_ID", "AUTH_ADMIN_EMAILS"):
        monkeypatch.delenv(k, raising=False)
    autopilot.stop(); autopilot.reset()

    def fake(round_id, playbook, started_by):
        save_round(round_id, playbook, started_by, "DONE")

    monkeypatch.setattr(routes_rounds, "_background_round", fake)
    return TestClient(app)


def _wait(fn, n=100):
    for _ in range(n):
        if fn():
            return True
        time.sleep(0.05)
    return False


def test_everyone_starts_with_200_and_costs_are_visible(client):
    j = client.get("/api/credits").json()
    assert j["balance"] == 200 == j["starting"] and j["costs"] == {"P1": 10, "P2": 10, "P3": 10, "NEW": 25}
    assert credits.cost_of("X-abc12345") == 25 and credits.cost_of("P2") == 10


def test_a_round_spends_credits_and_new_ai_attacks_cost_more(client):
    r = client.post("/api/rounds", json={"playbook": "P1"}).json()
    assert r["credits_charged"] == 10 and r["credits_left"] == 190
    r = client.post("/api/rounds", json={"playbook": "NEW"}).json()
    assert r["credits_charged"] == 25 and r["credits_left"] == 165
    j = client.get("/api/credits").json()
    assert j["balance"] == 165 and j["spent"] == 35 and j["history"][0]["delta"] == -25


def test_out_of_credits_is_refused_with_a_clear_message_and_changes_nothing(client):
    credits.charge("demo@local", 195, "test")
    r = client.post("/api/rounds", json={"playbook": "P1"})
    assert r.status_code == 402 and "costs 10" in r.json()["detail"] and "you have 5" in r.json()["detail"]
    assert client.get("/api/credits").json()["balance"] == 5
    assert credits.cost_of("P1") == 10


def test_safety_actions_never_cost_credits(client):
    credits.charge("demo@local", 200, "drain")
    assert client.get("/api/credits").json()["balance"] == 0
    for url in ("/api/ledger/verify", "/api/patches", "/api/versions", "/api/rounds"):
        assert client.get(url).status_code == 200
    r = client.post("/api/rollback?to_version=v1&checker=bob")                       # a person can always roll back
    assert r.status_code != 402
    assert client.get("/api/credits").json()["balance"] == 0


def test_a_crashed_round_is_refunded_once(client, monkeypatch):
    def crash(round_id, playbook, started_by):
        save_round(round_id, playbook, started_by, "ERROR: boom")
    monkeypatch.setattr(routes_rounds, "_background_round", crash)
    client.post("/api/rounds", json={"playbook": "P1"})
    assert _wait(lambda: client.get("/api/credits").json()["balance"] == 200)
    rid = next(h["ref"] for h in client.get("/api/credits").json()["history"] if h["delta"] > 0)
    credits.refund("demo@local", 10, "again", ref=rid)                               # same round: no second refund
    assert client.get("/api/credits").json()["balance"] == 200


def test_each_user_has_their_own_balance(client, monkeypatch):
    credits.charge("a@x.com", 50, "t")
    assert credits.account("a@x.com")["balance"] == 150 and credits.account("b@x.com")["balance"] == 200


def test_autopilot_spends_per_round_and_stops_when_out(client):
    credits.charge("demo@local", 175, "t")                                           # 25 left: P1 (10) + P2 (10) then 5 is not enough for P3
    client.post("/api/autopilot/start", json={"rounds": 5, "interval_s": 0, "playbooks": ["P1", "P2", "P3"]})
    assert _wait(lambda: not client.get("/api/autopilot").json()["running"])
    st = client.get("/api/autopilot").json()
    assert st["done"] == 2 and "out of credits" in st["note"] and st["log"][0]["state"] == "OUT_OF_CREDITS"
    assert client.get("/api/credits").json()["balance"] == 5


def test_only_admins_can_top_up_when_sign_in_is_on(client, monkeypatch):
    assert client.post("/api/credits/grant", json={"amount": 50}).json()["balance"] == 250      # local demo: open
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "x.apps.googleusercontent.com")
    tok = auth.make_session({"email": "alice@bank.com", "name": "A", "picture": None})
    client.cookies.set(auth.COOKIE, tok)
    assert client.post("/api/credits/grant", json={"amount": 50}).status_code == 403
    monkeypatch.setenv("AUTH_ADMIN_EMAILS", "alice@bank.com")
    assert client.post("/api/credits/grant", json={"amount": 50, "email": "bob@bank.com"}).json() == {"user": "bob@bank.com", "balance": 250}
    assert client.get("/api/credits").json()["user"] == "alice@bank.com"


def test_digest_welcomes_new_users_then_reports_what_happened_since(client):
    d = client.get("/api/digest").json()
    assert d["first_visit"] and d["worth_showing"] and d["balance"] == 200
    client.post("/api/digest/seen")
    d = client.get("/api/digest").json()
    assert not d["first_visit"] and d["rounds"] == 0 and not d["worth_showing"]
    save_round("rnd-dig1", "X-abc12345", "autopilot", "NO_SAFE_PATCH")
    save_round("rnd-dig2", "P1", "autopilot", "DONE")
    time.sleep(1.1)
    client.post("/api/digest/seen")
    time.sleep(1.1)                                                                  # round timestamps have 1-second resolution
    save_round("rnd-dig3", "X-abc12345", "autopilot", "AWAITING_APPROVAL")
    d = client.get("/api/digest").json()
    assert d["rounds"] == 1 and d["ai_attacks"] == 1 and d["holes_found"] == 1 and d["worth_showing"]
