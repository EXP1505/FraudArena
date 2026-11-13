"""Fidelity of the simulated world vs the RBIH friction tables (fa/world/fidelity.py)."""
from __future__ import annotations

import numpy as np
import pytest

from fa.world import fidelity as fid

TABLES = {
    "amount_ratio_30d": [{"op": ">", "threshold": 2.0, "legit_flagged_pct_test": 10.0, "mule_flagged_pct_test": 40.0},
                         {"op": ">", "threshold": 5.0, "legit_flagged_pct_test": 2.0, "mule_flagged_pct_test": 20.0}],
    "n_pay_1h": [{"op": ">", "threshold": 1.0, "legit_flagged_pct_test": 5.0, "mule_flagged_pct_test": 50.0}],
}
CFG = {"tolerance_pp": 10.0, "close_at": 75, "drifting_at": 50}


def _honest(ratio_hi: float, n: int = 1000) -> dict:
    """n payments; `ratio_hi` fraction have ratio > 5 (and a proportional share > 2)."""
    k = int(n * ratio_hi)
    return {"amount_ratio_30d": np.array([6.0] * k + [3.0] * int(n * 0.08) + [1.0] * (n - k - int(n * 0.08))),
            "n_pay_1h": np.array([2.0] * 50 + [0.0] * (n - 50))}


def test_matching_world_scores_high_and_wrong_world_scores_low():
    good = fid.compare(_honest(0.02), None, TABLES, CFG)
    bad = fid.compare(_honest(0.60), None, TABLES, CFG)
    assert good["available"] and good["score"] > bad["score"]
    assert good["score"] >= 75 and good["band"] == "close"
    assert bad["score"] <= 50 and bad["band"] != "close"


def test_unrecorded_signals_are_not_measurable_and_not_scored():
    r = fid.compare(_honest(0.02), None, TABLES, CFG)
    dev = next(f for f in r["features"] if f["feature"] == "device_changed_24h")
    assert dev["measurable"] is False and "score" not in dev
    assert r["measured_features"] == 2 and r["total_features"] == 13


def test_attack_realism_flags_attacks_that_are_weaker_or_stronger_than_real_mules():
    weak = {"amount_ratio_30d": np.array([1.0] * 100), "n_pay_1h": np.array([0.0] * 100)}
    strong = {"amount_ratio_30d": np.array([9.0] * 100), "n_pay_1h": np.array([5.0] * 100)}
    like = {"amount_ratio_30d": np.array([9.0] * 40 + [1.0] * 60), "n_pay_1h": np.array([5.0] * 50 + [0.0] * 50)}
    f = lambda a: next(x for x in fid.compare(_honest(0.02), a, TABLES, CFG)["features"] if x["feature"] == "n_pay_1h")
    assert "weaker" in f(weak)["attack_note"]
    assert "stronger" in f(strong)["attack_note"]
    assert "look like" in f(like)["attack_note"]


def test_no_tables_means_unavailable_not_a_made_up_score():
    r = fid.compare(_honest(0.02), None, {}, CFG)
    assert r["available"] is False and "score" not in r


def test_rule_check_refuses_numbers_measured_at_a_different_threshold():
    ev = {"feature": "amount_ratio_30d", "legit_flagged_pct_test": 2.0}
    same = {"id": "A", "title": "t", "when": [{"f": "amount_ratio_30d", "op": ">=", "v": 5.0}], "evidence": ev}
    tightened = {"id": "B", "title": "t", "when": [{"f": "amount_ratio_30d", "op": ">=", "v": 2.0}], "evidence": ev}
    out = {r["rule_id"]: r for r in fid.rule_check(_honest(0.02), [same, tightened], TABLES)}
    assert out["A"]["checked"] is True and out["A"]["rbih_friction_pct"] == 2.0
    assert out["B"]["checked"] is False and "not comparable" in out["B"]["note"]
    assert fid.evidence_matches(same, TABLES) and not fid.evidence_matches(tightened, TABLES)


def test_real_report_is_deterministic_and_honest():
    if fid.load_real_tables() is None:
        pytest.skip("RBIH bundle not present")
    a, b = fid.report(), fid.report()
    assert a["score"] == b["score"] and a["available"]
    assert 0 <= a["score"] <= 100 and a["measured_features"] < a["total_features"]
    assert any(not r["checked"] for r in a["rule_check"])          # R2/R6 evidence does not match their thresholds
    assert a["limits"]


def test_fidelity_endpoints_and_signed_certificate():
    if fid.load_real_tables() is None:
        pytest.skip("RBIH bundle not present")
    import time
    from fastapi.testclient import TestClient
    from api.main import app
    from fa.release import rulebook as rb
    with TestClient(app) as c:
        for _ in range(120):
            r = c.get("/api/fidelity").json()
            if r["status"] == "done":
                break
            time.sleep(0.5)
        assert r["status"] == "done" and r["score"] is not None
        doc = c.get("/api/fidelity/export").json()
        assert rb.check(doc)["authentic"]
        doc["report"]["score"] = 100
        assert rb.check(doc)["authentic"] is False
        assert c.get("/api/fidelity/export?format=pdf").content[:4] == b"%PDF"
        pol = c.get("/api/policy").json()["rules"]
        flags = {x["id"]: x["evidence_valid"] for x in pol}
        assert flags["R6"] is False and flags["R1"] is True
