"""Owner: M4. Rule engine, rule loader and baseline rule set v1.

Pure-evaluation tests use hand-written feature dicts; integration tests use M3's
real state/features so the engine and the feature code are checked together.
"""
from __future__ import annotations

import json

import pytest
from pydantic import ValidationError

from fa.contracts import Cond, Event, Rule, RuleSet
from fa.core.engine import decide, decide_shadow, decide_with_features, evaluate, rule_fires
from fa.core.state import new_state
from fa.rules.loader import (BASELINE_PATH, baseline_rules_from_params, load_baseline,
                             rules_from_dicts)


def rule(rid, action, *conds):
    return Rule(id=rid, action=action, when=[Cond(f=f, op=op, v=v) for f, op, v in conds])


# ------------------------------------------------------------------ pure evaluation

def test_allow_when_nothing_fires():
    assert evaluate({"n_pay_1h": 1}, [rule("A", "hold", ("n_pay_1h", ">=", 5))]) == ("allow", [])


def test_block_beats_hold():
    rules = [rule("H", "hold", ("n_pay_1h", ">=", 1)), rule("B", "block", ("n_pay_1h", ">=", 1))]
    assert evaluate({"n_pay_1h": 3}, rules) == ("block", ["B"])


def test_hold_beats_allow_and_lists_all_firing_holds_in_order():
    rules = [rule("H1", "hold", ("n_pay_1h", ">=", 1)), rule("H2", "hold", ("n_pay_1h", ">=", 2)),
             rule("H3", "hold", ("n_pay_1h", ">=", 9))]
    assert evaluate({"n_pay_1h": 3}, rules) == ("hold", ["H1", "H2"])


def test_all_conditions_must_hold():
    r = rule("R", "hold", ("amount_ratio_30d", ">=", 3), ("payee_age_h", "<", 1))
    assert not rule_fires(r, {"amount_ratio_30d": 5, "payee_age_h": 2})
    assert not rule_fires(r, {"amount_ratio_30d": 1, "payee_age_h": 0})
    assert rule_fires(r, {"amount_ratio_30d": 5, "payee_age_h": 0})


@pytest.mark.parametrize("op,val,expected", [
    ("<", 4.9, True), ("<", 5, False), ("<=", 5, True), ("<=", 5.1, False),
    (">", 5.1, True), (">", 5, False), (">=", 5, True), (">=", 4.9, False),
    ("==", 5, True), ("==", 4, False),
])
def test_operator_boundaries(op, val, expected):
    assert rule_fires(rule("R", "hold", ("sum_1h", op, 5)), {"sum_1h": val}) is expected


def test_missing_feature_never_fires():
    assert not rule_fires(rule("R", "hold", ("sum_1h", ">=", 0)), {})


def test_boolean_flag_compares_as_number():
    r = rule("R", "hold", ("night_flag", "==", 1))
    assert rule_fires(r, {"night_flag": 1.0})
    assert not rule_fires(r, {"night_flag": 0.0})


def test_max_four_conditions_enforced_by_contract():
    conds = [Cond(f="sum_1h", op=">=", v=i) for i in range(5)]
    with pytest.raises(ValidationError):
        Rule(id="X", action="hold", when=conds)


def test_unknown_feature_rejected_by_contract():
    with pytest.raises(ValidationError):
        Cond(f="not_a_feature", op=">", v=1)


# ------------------------------------------------------------------ loader / baseline

def test_baseline_file_matches_params_and_has_six_rules():
    from_file = load_baseline()
    assert from_file.version == "v1"
    assert [r.id for r in from_file.rules] == ["R1", "R2", "R3", "R4", "R5", "R6"]
    assert from_file.rules == baseline_rules_from_params()


def test_baseline_file_is_plain_list_for_m2():
    data = json.loads(BASELINE_PATH.read_text())
    assert isinstance(data, list) and data[0]["when"][0].keys() >= {"f", "op", "v"}


def test_baseline_actions():
    by_id = {r.id: r.action for r in load_baseline().rules}
    assert by_id == {"R1": "hold", "R2": "hold", "R3": "block", "R4": "hold", "R5": "block", "R6": "hold"}


def test_loader_rejects_bad_rules():
    with pytest.raises(ValidationError):
        rules_from_dicts([{"id": "X", "action": "hold", "when": [{"f": "bogus", "op": ">", "v": 1}]}])
    with pytest.raises(ValidationError):
        rules_from_dicts([{"id": "X", "action": "allow", "when": [{"f": "sum_1h", "op": ">", "v": 1}]}])
    with pytest.raises(ValidationError):
        rules_from_dicts([{"id": "X", "action": "hold", "when": [{"f": "sum_1h", "op": "!=", "v": 1}]}])
    ok = {"id": "X", "action": "hold", "when": [{"f": "sum_1h", "op": ">", "v": 1}]}
    with pytest.raises(ValueError):
        rules_from_dicts([ok, ok])


# ------------------------------------------------------------------ with M3's real state/features

def ev(i, ts, typ="payment", account="a1", payee="p1", amount=1000, device="d1"):
    return Event(event_id=f"e{i}", ts=ts, type=typ, account=account, payee=payee, amount=amount, device=device)


def test_normal_payment_allowed_under_baseline():
    d = decide(new_state(), ev(1, 100_000), load_baseline())
    assert (d.decision, d.fired, d.version) == ("allow", [], "v1")
    assert d.latency_us >= 0


def test_large_payment_to_new_payee_is_held():
    st, rs = new_state(), load_baseline()
    for i in range(3):                                   # build a 30-day average of 1000
        decide(st, ev(i, 100_000 + i * 7200), rs)
    decide(st, ev(10, 200_000, typ="add_payee", payee="new-landlord", amount=0), rs)
    d = decide(st, ev(11, 200_600, payee="new-landlord", amount=30_000), rs)
    assert d.decision == "hold" and "R1" in d.fired
    assert st.accounts["a1"].pending, "held payment must go to the pending list"


def test_rapid_payments_get_blocked():
    st, rs = new_state(), load_baseline()
    actions = [decide(st, ev(i, 100_000 + i * 60), rs).decision for i in range(14)]
    assert actions[0] == "allow"
    assert "block" in actions
    assert actions.index("block") == 12                  # R3: n_pay_1h >= 12 on the 13th payment


def test_decide_applies_state_but_shadow_does_not():
    st, rs = new_state(), load_baseline()
    decide(st, ev(1, 100_000), rs)
    n_before = len(st.accounts["a1"].recent_pays)
    decide_shadow(st, ev(2, 100_100), rs)
    assert len(st.accounts["a1"].recent_pays) == n_before
    decide(st, ev(2, 100_100), rs)
    assert len(st.accounts["a1"].recent_pays) == n_before + 1


def test_decide_with_features_returns_the_features():
    d, feats = decide_with_features(new_state(), ev(1, 100_000), load_baseline())
    assert d.decision == "allow" and "amount_ratio_30d" in feats and "n_pay_1h" in feats


def test_decide_is_deterministic():
    def run():
        st, rs = new_state(), load_baseline()
        return [(d.decision, d.fired) for d in (decide(st, ev(i, 100_000 + i * 60), rs) for i in range(20))]

    assert run() == run()


def test_candidate_rule_set_changes_outcome_without_touching_state():
    st = new_state()
    base = load_baseline()
    night = RuleSet(version="v2", rules=[*base.rules, rule("N", "hold", ("night_flag", "==", 1))])
    e = ev(1, 3 * 3600)                                   # 03:00
    assert decide_shadow(st, e, base).decision == "allow"
    assert decide_shadow(st, e, night).decision == "hold"
    assert not st.accounts
