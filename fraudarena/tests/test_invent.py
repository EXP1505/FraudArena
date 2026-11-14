"""Owner: M4. LLM-invented playbooks and the autopilot. No test touches data/ or the network."""
from __future__ import annotations

import time
import warnings

import pytest

from fa.agents import llm
from fa.agents.search import get_plan, worst_case
from fa.plans import invent
from fa.plans.validator import validate
from fa.rules.loader import active

warnings.filterwarnings("ignore")


@pytest.fixture(autouse=True)
def _fresh(tmp_path, monkeypatch):
    monkeypatch.setenv("FA_INVENTED_PATH", str(tmp_path / "inv.json"))
    monkeypatch.delenv("LLM_OFFLINE_FALLBACK", raising=False)
    monkeypatch.setattr(llm.httpx, "post", lambda *a, **k: (_ for _ in ()).throw(AssertionError("network")))


def _no_key(monkeypatch, tmp_path):
    from fa.config import load_config
    base = load_config()
    cfg = base.model_copy(update={"llm_api_key": None, "params": {**base.params, "agents": {**base.section("agents"), "cache_dir": str(tmp_path / "c")}}})
    monkeypatch.setattr(llm, "load_config", lambda *a, **k: cfg)
    monkeypatch.setattr("fa.config.load_config", lambda *a, **k: cfg)
    return cfg


def test_every_idea_in_the_bank_is_valid_and_builds_a_valid_plan():
    for idea in invent.IDEA_BANK:
        clean, bad = invent._clean(idea)
        assert clean and not bad, (idea["name"], bad)
        spec = invent._finish(clean, "offline-stand-in", 0)
        for scale in ({}, {"amount_scale": 2.0, "delay_scale": 3.0}, {"amount_scale": 0.3, "delay_scale": 0.25}):
            plan = invent.build_invented(spec["id"], scale, 1)
            assert validate(plan) == [], (idea["name"], scale, validate(plan))
            assert plan.playbook == spec["id"] and plan.steps[-1].act == "cashout"


@pytest.mark.parametrize("raw,fragment", [
    ({"name": "x", "steps": []}, "non-empty"),
    ({"name": "x", "steps": [{"act": "hack", "actor": "victim", "delay_s": 0}]}, "act must be"),
    ({"name": "x", "steps": [{"act": "pay", "actor": "victim", "delay_s": 0, "amount_mult": 1}]}, "cash-out"),
    ({"name": "x", "steps": [{"act": "cashout", "actor": "victim", "delay_s": 0}]}, "only a mule"),
    ({"name": "x", "steps": [{"act": "pay", "actor": "victim", "delay_s": 0, "amount_mult": 999},
                             {"act": "cashout", "actor": "mule", "delay_s": 0}]}, "usual payment"),
    ({"name": "x", "steps": [{"act": "pay", "actor": "victim", "delay_s": 99999, "amount_mult": 1},
                             {"act": "cashout", "actor": "mule", "delay_s": 0}]}, "waiting"),
    ({"name": "x", "steps": [{"act": "pay", "actor": "victim", "delay_s": 0, "amount_mult": 1}] * 13}, "at most"),
])
def test_bad_llm_answers_are_rejected_with_a_reason(raw, fragment):
    clean, bad = invent._clean(raw)
    assert clean is None and any(fragment in b for b in bad), bad


def test_without_a_key_the_idea_bank_is_used_and_labelled(monkeypatch, tmp_path):
    _no_key(monkeypatch, tmp_path)
    a, b = invent.invent(seed=1), invent.invent(seed=1)
    assert a["source"] == "offline-stand-in" and a["id"] != b["id"]       # asks for something different the second time
    assert invent.approach_for(invent.build_invented(a["id"], {}, 0))["origin"].startswith("built-in idea")
    assert {s["id"] for s in invent.all_specs()} == {a["id"], b["id"]}


def test_an_llm_answer_is_validated_registered_and_retried(monkeypatch, tmp_path):
    cfg = _no_key(monkeypatch, tmp_path)
    cfg2 = cfg.model_copy(update={"llm_api_key": "k"})
    monkeypatch.setattr(llm, "load_config", lambda *a, **k: cfg2)
    monkeypatch.setattr("fa.config.load_config", lambda *a, **k: cfg2)
    answers = iter([{"name": "bad", "approach": "", "why_it_might_work": "", "steps": []},
                    {**invent.IDEA_BANK[0], "name": "AI idea"}])
    prompts = []
    monkeypatch.setattr(llm, "_call_anthropic", lambda prompt, *a: prompts.append(prompt) or next(answers))
    spec = invent.invent(seed=3)
    assert spec["source"] == "llm" and spec["name"] == "AI idea" and len(prompts) == 2
    assert "rejected" in prompts[1]                                       # the retry tells it what was wrong
    assert invent.approach_for(invent.build_invented(spec["id"], {}, 0))["origin"] == "invented by the attacker AI"


def test_the_search_runs_on_an_invented_playbook_and_finds_a_loss(monkeypatch, tmp_path):
    _no_key(monkeypatch, tmp_path)
    spec = invent.invent(seed=0)
    trace = worst_case(spec["id"], active(), trials=15, seed=7)
    plan = get_plan(trace.plan_id)
    assert plan is not None and plan.playbook == spec["id"] and validate(plan) == []
    assert set(plan.params) >= {"amount_scale", "delay_scale"}
    assert trace.loss_through >= 0


def test_approach_for_builtin_playbooks_lists_what_the_search_tuned():
    from fa.plans.playbooks import PARAM_RANGES, build_plan
    for pb, ranges in PARAM_RANGES.items():
        plan = build_plan(pb, {k: (lo + hi) / 2 for k, (lo, hi) in ranges.items()}, 1)
        ap = invent.approach_for(plan)
        assert ap["origin"] == "built-in" and ap["idea"] and ap["why"] and len(ap["tuned"]) >= 3
        assert all(t["label"] and t["value"] for t in ap["tuned"])


def test_an_unknown_playbook_id_is_rejected():
    from fa.contracts import Plan
    with pytest.raises(ValueError):
        invent.build_invented("X-deadbeef", {}, 0)
    with pytest.raises(Exception):
        Plan(plan_id="p", playbook="evil; drop", seed=0, steps=[])


# ------------------------------------------------------------------ API + autopilot

@pytest.fixture
def client(tmp_path, monkeypatch):
    from fastapi.testclient import TestClient
    from api import autopilot
    from api.main import app
    from api.db import init_db
    init_db()
    autopilot.stop(); autopilot.reset()
    return TestClient(app)


def test_playbooks_endpoint_lists_builtin_and_invented(client, monkeypatch, tmp_path):
    _no_key(monkeypatch, tmp_path)
    assert [p["id"] for p in client.get("/api/playbooks").json()] == ["P1", "P2", "P3"]
    spec = invent.invent(seed=0)
    rows = client.get("/api/playbooks").json()
    assert rows[-1]["id"] == spec["id"] and rows[-1]["idea"] and rows[-1]["why"] and rows[-1]["steps"]


def test_autopilot_runs_rounds_in_turn_and_logs_them(client, monkeypatch):
    from api import autopilot, routes_rounds
    from api.db import get_round, save_round

    ran = []

    def fake(round_id, playbook, started_by):
        ran.append((playbook, started_by))
        save_round(round_id, "X-abc12345" if playbook == "NEW" else playbook, started_by, "DONE")

    monkeypatch.setattr(routes_rounds, "_background_round", fake)
    r = client.post("/api/autopilot/start", json={"rounds": 4, "interval_s": 0, "playbooks": ["P1", "NEW"]})
    assert r.status_code == 200
    for _ in range(100):
        if not client.get("/api/autopilot").json()["running"]:
            break
        time.sleep(0.05)
    st = client.get("/api/autopilot").json()
    assert not st["running"] and st["done"] == 4
    assert ran == [("P1", "autopilot"), ("NEW", "autopilot"), ("P1", "autopilot"), ("NEW", "autopilot")]
    assert st["log"][0]["state"] == "DONE" and {e["playbook"] for e in st["log"]} == {"P1", "X-abc12345"}
    assert get_round(st["log"][0]["round_id"])["started_by"] == "autopilot"


def test_autopilot_pauses_when_proposals_pile_up_and_can_be_stopped(client, monkeypatch):
    from api import autopilot, routes_rounds
    monkeypatch.setattr(autopilot, "_waiting", lambda: 5)
    monkeypatch.setattr(routes_rounds, "_background_round", lambda *a: (_ for _ in ()).throw(AssertionError("must not run")))
    client.post("/api/autopilot/start", json={"rounds": 3, "interval_s": 0, "max_pending": 3})
    time.sleep(0.3)
    st = client.get("/api/autopilot").json()
    assert st["running"] and "Paused" in st["note"] and st["done"] == 0
    client.post("/api/autopilot/stop")
    for _ in range(100):
        if not client.get("/api/autopilot").json()["running"]:
            break
        time.sleep(0.05)
    assert not client.get("/api/autopilot").json()["running"]


def test_autopilot_validates_its_input(client):
    assert client.post("/api/autopilot/start", json={"playbooks": ["P9"]}).status_code == 422
    assert client.post("/api/autopilot/start", json={"rounds": 999}).status_code == 422


def test_autopilot_survives_a_crashing_round(client, monkeypatch):
    from api import routes_rounds
    monkeypatch.setattr(routes_rounds, "_background_round", lambda *a: (_ for _ in ()).throw(RuntimeError("boom")))
    client.post("/api/autopilot/start", json={"rounds": 2, "interval_s": 0})
    for _ in range(100):
        if not client.get("/api/autopilot").json()["running"]:
            break
        time.sleep(0.05)
    st = client.get("/api/autopilot").json()
    assert not st["running"] and st["log"][0]["state"].startswith("ERROR")
