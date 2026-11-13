"""Rulebook export / verify / import, attack library, PDF and the snapshot before a world reset."""
from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient

from api.main import app
from fa.release import rulebook as rb
from fa.release.versions import default_store


@pytest.fixture()
def client():
    with TestClient(app) as c:
        yield c


def test_export_json_is_signed_and_authentic(client):
    r = client.get("/api/versions/v1/export?format=json")
    assert r.status_code == 200 and "attachment" in r.headers["content-disposition"]
    doc = r.json()
    assert doc["format"] == rb.RULEBOOK_FORMAT and doc["version"] == "v1" and doc["rules"]
    assert all(x["title"] and x["customer_message"] for x in doc["rules"])
    assert rb.check(doc)["authentic"] is True
    v = client.post("/api/rulebook/verify", json=doc).json()
    assert v["authentic"] and v["this_server"]


def test_tampered_rulebook_is_detected(client):
    doc = client.get("/api/versions/v1/export").json()
    doc["rules"][0]["when"][0]["v"] = 9999
    v = client.post("/api/rulebook/verify", json=doc).json()
    assert v["authentic"] is False and "modified" in v["reason"]
    assert client.post("/api/rulebook/import?maker=alice", json=doc).status_code == 400


def test_export_csv_md_pdf(client):
    csv_r = client.get("/api/versions/v1/export?format=csv")
    assert csv_r.text.splitlines()[0].startswith("version,rule_id,title")
    md = client.get("/api/versions/v1/export?format=md").text
    assert md.startswith("# FraudArena rulebook v1") and "Customer sees" in md
    pdf = client.get("/api/versions/v1/export?format=pdf")
    assert pdf.content[:4] == b"%PDF" and len(pdf.content) > 2000
    assert client.get("/api/versions/v99/export").status_code == 404


def test_import_never_changes_the_active_version(client):
    doc = client.get("/api/versions/v1/export").json()
    before = default_store().active_version()
    r = client.post("/api/rulebook/import?maker=alice", json=doc)
    assert r.status_code == 200
    body = r.json()
    assert body["provenance"]["authentic"] and body["proposals"]
    assert default_store().active_version() == before
    for p in body["proposals"]:
        patch = default_store().get_patch(p["patch_id"])
        assert patch["state"] != "ACTIVE" and patch["starter"] == "alice"
        assert patch["rule"]["source"] == "imported"


def test_import_rejects_contract_violations(client):
    doc = client.get("/api/versions/v1/export").json()
    doc["rules"][0]["when"][0]["f"] = "not_a_feature"
    doc = {k: v for k, v in doc.items() if k not in ("sha256", "signature", "public_key")}
    assert client.post("/api/rulebook/import?maker=bob", json=rb.seal(doc)).status_code == 400
    assert client.post("/api/rulebook/import?maker=bob", json={"format": "x"}).status_code == 400


def test_attack_library_roundtrip(client):
    from fa.plans.playbooks import PARAM_RANGES, build_plan
    from fa.verify import regression

    regression.clear()
    params = {k: (lo + hi) / 2 for k, (lo, hi) in PARAM_RANGES["P1"].items()}
    plan = build_plan("P1", params, 1)
    lib_id = plan.plan_id
    assert regression.add(plan)
    lib = client.get("/api/attacks").json()
    assert [a["plan_id"] for a in lib] == [lib_id] and "summary" in lib[0]
    exp = client.get("/api/attacks/export").json()
    assert rb.check(exp)["authentic"]
    regression.clear()
    assert client.get("/api/attacks").json() == []
    r = client.post("/api/attacks/import", json=exp).json()
    assert r["added"] == [lib_id] and not r["rejected"]
    again = client.post("/api/attacks/import", json=exp).json()
    assert again["already_present"] == [lib_id]
    assert client.post("/api/attacks/" + lib_id + "/replay").json()["plan_id"] == lib_id
    bad = json.loads(json.dumps(exp))
    bad["plans"][0]["steps"] = []
    assert client.post("/api/attacks/import", json=bad).status_code == 400   # hash no longer matches
    regression.clear()


def test_reset_saves_a_signed_rulebook_snapshot(client):
    r = client.post("/api/world/reset").json()
    assert r["snapshot"] and r["snapshot"]["version"]
    names = [s["name"] for s in client.get("/api/snapshots").json()]
    assert any(n.endswith(".pdf") for n in names) and any(n.endswith(".json") for n in names)
    js = next(n for n in names if n.endswith(".json"))
    doc = client.get(f"/api/snapshots/{js}").json()
    assert rb.check(doc)["authentic"]
    assert client.get("/api/snapshots/../../etc/passwd").status_code in (404, 422)


def test_stress_test_is_deterministic_and_honest():
    from fa.rules.loader import load_baseline
    from fa.stress import stress_test
    cfg = {"seeds": [7001, 7002], "trials": 40}
    a, b = stress_test(load_baseline(), cfg), stress_test(load_baseline(), cfg)
    assert a == b and a["n"] == 6 and 0 <= a["wilson_lo"] <= a["rate"] <= a["wilson_hi"] <= 1
    assert a["worst_loss"] > 0 and a["stopped"] < a["n"]          # the unpatched baseline must not look perfect
    assert set(a["per_playbook"]) == {"P1", "P2", "P3"}
    assert not (set(a["seeds"]) & {42, 9001})                      # held out from search and gates


def test_stress_endpoint_runs_in_background(client):
    import time
    r = client.get("/api/stress").json()
    assert r["status"] in ("running", "done")
    for _ in range(120):
        r = client.get("/api/stress").json()
        if r["status"] != "running":
            break
        time.sleep(0.5)
    assert r["status"] == "done" and r["n"] == 15 and "wilson_lo" in r
