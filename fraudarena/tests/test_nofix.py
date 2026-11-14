"""Owner: M4. A round that ends with no safe fix explains itself."""
from __future__ import annotations

import warnings

from fa.release import nofix

warnings.filterwarnings("ignore")


def test_diagnose_gives_a_reason_a_closest_rule_and_ideas(monkeypatch, tmp_path):
    from fa.agents.search import get_plan, worst_case
    from fa.plans import invent
    from fa.rules.loader import active

    monkeypatch.setenv("FA_INVENTED_PATH", str(tmp_path / "inv.json"))
    clean, _ = invent._clean(invent.IDEA_BANK[0])               # slow drip: the kind that has no cheap fix
    spec = invent._finish(clean, "offline-stand-in", 0)
    rs = active()
    trace = worst_case(spec["id"], rs, trials=12, seed=7)
    rep = nofix.diagnose(trace, rs, get_plan(trace.plan_id))
    assert rep["loss_text"].startswith("₹") and rep["why"] and rep["ideas"]
    assert rep["approach"]["name"] == spec["name"]
    if rep["best"]:
        assert rep["best"]["rule"] and rep["best"]["stops"].startswith("₹")
        assert all(p["gate"] in nofix.GATE_PLAIN and p["text"] for p in rep["best"]["problems"])
        assert rep["tried"] >= 1


def test_store_roundtrip_and_endpoint(monkeypatch, tmp_path):
    from fastapi.testclient import TestClient
    from api.main import app

    monkeypatch.setenv("FA_NOFIX_PATH", str(tmp_path / "n.json"))
    nofix.save("rnd-1", {"why": "because", "loss_text": "₹1.00", "ideas": [], "best": None})
    c = TestClient(app)
    assert c.get("/api/rounds/rnd-1/nofix").json()["why"] == "because"
    assert c.get("/api/rounds/rnd-nope/nofix").status_code == 404
    nofix.clear()
    assert nofix.get("rnd-1") is None
