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
