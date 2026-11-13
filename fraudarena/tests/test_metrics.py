# Owner: M3. hold_rate, wilson, wcel, local rule evaluation.
import pytest

from fa.metrics import hold_rate, local_decide, wcel, wilson


def test_wilson_known_values():
    lo, hi = wilson(10, 100)
    assert lo == pytest.approx(0.0552, abs=1e-3) and hi == pytest.approx(0.1744, abs=1e-3)
    assert wilson(0, 0) == (0.0, 0.0)


def test_hold_rate_counts_hold_and_block():
    p, lo, hi = hold_rate(["allow"] * 97 + ["hold", "block", "hold"])
    assert p == pytest.approx(0.03) and lo < 0.03 < hi
    p, _, _ = hold_rate([{"decision": "hold"}, {"decision": "allow"}])
    assert p == 0.5


def test_wcel():
    assert wcel([{"loss_through": 5}, {"loss_through": 9}, {"loss_through": 0}]) == 9
    assert wcel([]) == 0


def test_local_decide_precedence():
    rs = {"rules": [
        {"id": "H", "action": "hold", "when": [{"f": "x", "op": ">=", "v": 1}]},
        {"id": "B", "action": "block", "when": [{"f": "x", "op": ">=", "v": 2}, {"f": "y", "op": "==", "v": 1}]},
    ]}
    assert local_decide({"x": 0, "y": 1}, rs) == ("allow", [])
    assert local_decide({"x": 1, "y": 1}, rs) == ("hold", ["H"])
    assert local_decide({"x": 2, "y": 1}, rs) == ("block", ["H", "B"])
    assert local_decide({"x": 2, "y": 0}, rs)[0] == "hold"


def test_detection_delay():
    from fa.contracts import Decision, Step, Trace
    from fa.metrics import detection_delay_s
    d = lambda x: Decision(event_id="e", decision=x, version="v")  # noqa: E731
    tr = Trace(plan_id="p", steps=[(Step(t=100, actor="victim", act="login"), {}, d("allow")),
                                   (Step(t=400, actor="victim", act="pay", amount=1), {}, d("hold"))])
    assert detection_delay_s(tr) == 300
    tr2 = Trace(plan_id="p", steps=[(Step(t=0, actor="victim", act="login"), {}, d("allow"))])
    assert detection_delay_s(tr2) is None


def test_experiment_rows_and_bench(tmp_path):
    from fa.metrics import bench, experiment
    from fa.rules.loader import load
    rows = experiment(load("v1"), trials=5, playbooks=("P1",))
    assert rows[0]["playbook"] == "P1" and rows[0]["hold_rate_lo"] <= rows[0]["hold_rate"] <= rows[0]["hold_rate_hi"]
    out = bench(n=500, out_path=str(tmp_path / "b.json"))
    assert out["events"] == 500 and 0 < out["p50_us"] <= out["p95_us"] <= out["p99_us"]
