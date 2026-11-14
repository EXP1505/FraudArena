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


# ------------------------------------------------------------------ the attacker adapts

def test_the_attacker_is_told_what_worked_and_what_was_blocked(monkeypatch, tmp_path):
    _no_key(monkeypatch, tmp_path)
    a = invent.invent(seed=0)
    b = invent.invent(seed=0)
    invent.record_outcome(a["id"], "v2", 0)                 # blocked
    invent.record_outcome(b["id"], "v2", 123456)            # got through
    fb = invent._feedback(invent.all_specs())
    assert "GOT MONEY THROUGH" in fb and b["name"] in fb and "BLOCKED" in fb and a["name"] in fb
    assert b["approach"][:40] in fb
    assert invent._feedback([]) == "" and invent._feedback([{"name": "x", "approach": "y"}]) == ""
    assert fb in invent._prompt([], [], fb)                 # and it reaches the model, which never sees the rules
    assert len(invent.get_spec(a["id"])["outcomes"]) == 1


def _stub_round(monkeypatch, tmp_path, losses):
    """Run the NEW round with the attacker's search results scripted: losses[i] for the i-th invented attack."""
    from fa import orchestrator
    from fa.contracts import Trace

    _no_key(monkeypatch, tmp_path)
    monkeypatch.setattr("fa.release.nofix.diagnose", lambda *a, **k: {"why": "stub"})
    monkeypatch.setattr("fa.release.nofix.save", lambda *a, **k: None)
    seq = iter(losses)
    monkeypatch.setattr(orchestrator, "worst_case",
                        lambda pb, rs, trials, seed: Trace(plan_id=f"pl-{pb}", steps=[], loss_through=next(seq), missed_step=0 if True else None))
    monkeypatch.setattr(orchestrator, "defend", lambda trace, rs: None)
    monkeypatch.setattr(orchestrator, "get_plan", lambda pid: None)
    return orchestrator


def test_a_new_ai_attack_round_keeps_trying_until_one_gets_through(monkeypatch, tmp_path):
    orch = _stub_round(monkeypatch, tmp_path, [0, 0, 5000])
    _rid, out = orch.run_round_detailed("NEW", "alice")
    assert out["state"] == "NO_SAFE_PATCH" and out["loss_through"] == 5000     # the third attack landed; the stub defender finds no fix
    outcomes = [s["outcomes"][-1]["loss"] for s in invent.all_specs()]
    assert outcomes == [0, 0, 5000] and len(invent.all_specs()) == 3


def test_a_round_gives_up_after_three_blocked_attacks(monkeypatch, tmp_path):
    orch = _stub_round(monkeypatch, tmp_path, [0, 0, 0, 0])
    _rid, out = orch.run_round_detailed("NEW", "alice")
    assert out["state"] == "DONE" and out["attacks_tried"] == 3 and len(invent.all_specs()) == 3


def test_a_round_stops_at_the_first_success(monkeypatch, tmp_path):
    orch = _stub_round(monkeypatch, tmp_path, [777, 0, 0])
    orch.run_round_detailed("NEW", "alice")
    assert len(invent.all_specs()) == 1


def test_earlier_attacks_are_retested_against_the_live_rules_once_per_version(monkeypatch, tmp_path):
    from fa.agents import search
    from fa.contracts import RuleSet

    _no_key(monkeypatch, tmp_path)
    a, b = invent.invent(seed=0), invent.invent(seed=0)
    calls = []

    def fake(pb, rs, trials, seed):
        calls.append(pb)
        from fa.contracts import Trace
        return Trace(plan_id="p", steps=[], loss_through=900 if pb == a["id"] else 0, missed_step=None)

    monkeypatch.setattr(search, "worst_case", fake)
    rs = RuleSet(version="v7", rules=[])
    invent.refresh_outcomes(rs, seed=1)
    assert sorted(calls) == sorted([a["id"], b["id"]])
    assert invent.get_spec(a["id"])["outcomes"][-1] == {"version": "v7", "loss": 900}
    invent.refresh_outcomes(rs, seed=1)                                   # same version: nothing re-run
    assert len(calls) == 2
    invent.refresh_outcomes(RuleSet(version="v8", rules=[]), seed=1)      # new version: re-tested
    assert len(calls) == 4
    fb = invent._feedback(invent.all_specs())
    assert a["name"] in fb.split("BLOCKED")[0] and b["name"] in fb.split("BLOCKED")[1]
