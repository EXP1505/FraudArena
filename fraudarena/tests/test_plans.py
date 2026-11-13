"""Owner: M1. Plan validator tests (malformed plans rejected), a hypothesis
property test (every mutator.variants() output still passes
validator.validate()), and executor.execute() against the real engine/rules
(M3's state/features, M4's engine landed, so these now run for real).
"""
from __future__ import annotations

from hypothesis import given, settings
from hypothesis import strategies as st

from fa.contracts import Plan, Step
from fa.core.state import new_state
from fa.plans.executor import execute
from fa.plans.mutator import variants
from fa.plans.playbooks import PARAM_RANGES, build_plan
from fa.plans.schema import MAX_STEPS
from fa.plans.validator import validate
from fa.rules.loader import load_baseline


def _valid_plan() -> Plan:
    return build_plan("P1", {k: (lo + hi) / 2 for k, (lo, hi) in PARAM_RANGES["P1"].items()}, seed=1)


def test_valid_plan_has_no_violations():
    assert validate(_valid_plan()) == []


def test_rejects_too_many_steps():
    base = _valid_plan()
    extra_steps = list(base.steps) + [
        Step(t=i, actor="victim", act="pay", payee="p", amount=1) for i in range(MAX_STEPS)
    ]
    bad = base.model_copy(update={"steps": extra_steps})
    violations = validate(bad)
    assert any("MAX_STEPS" in v for v in violations)


def test_rejects_non_sandbox_actor():
    base = _valid_plan()
    steps = list(base.steps)
    steps[0] = steps[0].model_copy(update={"actor": "bank_employee"})
    bad = base.model_copy(update={"steps": steps})
    violations = validate(bad)
    assert any("sandbox role" in v for v in violations)


def test_rejects_horizon_over_72h():
    base = _valid_plan()
    steps = list(base.steps)
    steps[-1] = steps[-1].model_copy(update={"t": steps[0].t + 73 * 3600})
    bad = base.model_copy(update={"steps": steps})
    violations = validate(bad)
    assert any("MAX_SPAN_SECONDS" in v for v in violations)


def test_rejects_amount_over_200x_victim_mean():
    base = _valid_plan()
    params = dict(base.params)
    params["victim_mean_amount"] = 1
    steps = list(base.steps)
    steps[-1] = steps[-1].model_copy(update={"amount": 10_000})
    bad = base.model_copy(update={"steps": steps, "params": params})
    violations = validate(bad)
    assert any("victim mean" in v for v in violations)


def test_rejects_empty_plan():
    base = _valid_plan()
    bad = base.model_copy(update={"steps": []})
    assert validate(bad) == ["plan has no steps"]


@given(seed=st.integers(min_value=0, max_value=10_000), n=st.integers(min_value=1, max_value=20))
@settings(max_examples=25)
def test_mutator_variants_stay_valid(seed, n):
    plan = _valid_plan()
    for variant in variants(plan, n, seed):
        assert validate(variant) == []


def _p1_plan(**overrides) -> Plan:
    params = {k: (lo + hi) / 2 for k, (lo, hi) in PARAM_RANGES["P1"].items()}
    params.update(overrides)
    return build_plan("P1", params, seed=7)


def test_execute_counts_cashout_once_not_every_hop():
    """loss_through is the cash-out amount, not test_amt + drain + cashout
    double-counted (regression: an earlier version summed every money step)."""
    plan = _p1_plan()
    rs = load_baseline()
    trace = execute(plan, new_state(), rs)

    drain_step = next(s for s in plan.steps if s.act == "cashout")
    assert trace.loss_through == drain_step.amount
    assert trace.missed_step is not None


def test_execute_blocked_plan_has_zero_loss():
    """A fan-out of 9 distinct payees in an hour trips baseline R5 (block)."""
    steps = [Step(t=0, actor="victim", act="login", device="new")]
    for i in range(9):
        payee = f"payee{i}"
        steps.append(Step(t=60 + i * 60, actor="victim", act="add_payee", payee=payee))
        steps.append(Step(t=90 + i * 60, actor="victim", act="pay", payee=payee, amount=100))
    plan = Plan(plan_id="pl-fanout", playbook="P1", seed=1, params={}, steps=steps)

    trace = execute(plan, new_state(), load_baseline())
    assert trace.loss_through == 0
    assert any(d.decision == "block" for _s, _f, d in trace.steps)


def test_execute_returns_real_features_per_step():
    plan = _p1_plan()
    trace = execute(plan, new_state(), load_baseline())
    _step, features, _decision = trace.steps[0]
    assert "amount_ratio_30d" in features and "night_flag" in features
