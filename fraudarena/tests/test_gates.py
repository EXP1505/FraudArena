"""Owner: M4. Gates G1 to G6: each accepts a good patch and rejects a deliberately
bad one (24h plan section 11). Plans run through M1's executor and M3's real
state/features; rules are tiny hand-made ones so every outcome is predictable.

A plan that starts at ts=0 happens at 00:00 (night_flag = 1); starting at
12:00 it does not. The "good" patch is therefore `hold if night_flag == 1`.
"""
from __future__ import annotations

import pytest

from fa.contracts import Cond, Event, Plan, Rule, RuleSet, Step
from fa.rules.loader import load_baseline
from fa.verify import gates
from fa.verify.regression import RegressionStore

NOON = 12 * 3600
BASE = load_baseline()


def mk_rule(rid, action, *conds):
    return Rule(id=rid, action=action, when=[Cond(f=f, op=op, v=v) for f, op, v in conds])


def cand(*extra):
    return RuleSet(version="v2", rules=[*BASE.rules, *extra])


NIGHT = mk_rule("R-night", "hold", ("night_flag", "==", 1))
IRRELEVANT = mk_rule("R-never", "hold", ("n_pay_1h", ">=", 999))


def attack(pid, start=0):
    return Plan(plan_id=pid, playbook="P1", seed=1, steps=[
        Step(t=start, actor="victim", act="login", device="new"),
        Step(t=start + 180, actor="victim", act="add_payee", payee="mule"),
        Step(t=start + 480, actor="victim", act="pay", payee="mule", amount=100),
        Step(t=start + 1080, actor="victim", act="pay", payee="mule", amount=4_800_000),
        Step(t=start + 2400, actor="mule", act="cashout", amount=4_800_000),
    ])


def noon_payment(i):
    return Event(event_id=f"n{i}", ts=NOON + i * 5, type="payment", account=f"acc{i}", payee="shop",
                 amount=1000, device="d1")


@pytest.fixture
def ctx():
    return {
        "base_rule_set": BASE,
        "plan": attack("pl-fail"),
        "regression_plans": [attack("pl-old")],
        "variants": [attack(f"pl-v{i}", start=i * 600) for i in range(10)],   # all within 00:00-02:00
        "normal_events": [noon_payment(i) for i in range(3000)],
        "golden_cases": [[noon_payment(i)] for i in range(5)],
    }


def test_baseline_does_not_stop_the_attack(ctx):
    """Sanity: there is a real gap for the patch to close."""
    assert not gates.g2_stops_attack(BASE, ctx).passed


# ---------------------------------------------------------------- G1

def test_g1_accepts_valid_rule(ctx):
    r = gates.g1_valid(cand(NIGHT), ctx)
    assert r.passed and r.evidence["checked"] == ["R-night"]


def test_g1_rejects_unknown_feature(ctx):
    bad = Rule.model_construct(id="R-bad", action="hold", rationale="", evidence={}, source="t", added_in="v2",
                               when=[Cond.model_construct(f="bogus_feature", op=">", v=1.0)])
    r = gates.g1_valid(cand(bad), ctx)
    assert not r.passed and "bogus_feature" in r.reason


def test_g1_rejects_bad_operator_and_too_many_conditions(ctx):
    op_bad = Rule.model_construct(id="R-op", action="hold", rationale="", evidence={}, source="t", added_in="v2",
                                  when=[Cond.model_construct(f="sum_1h", op="!=", v=1.0)])
    many = Rule.model_construct(id="R-many", action="hold", rationale="", evidence={}, source="t", added_in="v2",
                                when=[Cond(f="sum_1h", op=">", v=i) for i in range(5)])
    assert "not allowed" in gates.g1_valid(cand(op_bad), ctx).reason
    assert "5 conditions" in gates.g1_valid(cand(many), ctx).reason


def test_g1_rejects_duplicate_of_existing_rule(ctx):
    dup = mk_rule("R-copy", "hold", ("amount_ratio_30d", ">=", 10))      # same as R1
    r = gates.g1_valid(cand(dup), ctx)
    assert not r.passed and "identical to existing rule R1" in r.reason


def test_g1_rejects_duplicate_id_and_empty_patch(ctx):
    same_id = mk_rule("R1", "hold", ("sum_1h", ">", 1))
    assert not gates.g1_valid(cand(same_id), ctx).passed
    assert not gates.g1_valid(BASE, ctx).passed


# ---------------------------------------------------------------- G2

def test_g2_accepts_patch_that_stops_the_attack(ctx):
    r = gates.g2_stops_attack(cand(NIGHT), ctx)
    assert r.passed and r.evidence["loss_through"] == 0


def test_g2_rejects_irrelevant_rule(ctx):
    r = gates.g2_stops_attack(cand(IRRELEVANT), ctx)
    assert not r.passed and r.evidence["loss_through"] > 0


def test_g2_fails_closed_without_plan(ctx):
    del ctx["plan"]
    r = gates.g2_stops_attack(cand(NIGHT), ctx)
    assert not r.passed and r.reason.startswith("missing context")


# ---------------------------------------------------------------- G3

def test_g3_accepts_when_old_attacks_stay_stopped(ctx):
    assert gates.g3_no_regression(cand(NIGHT), ctx).passed


def test_g3_rejects_rule_set_that_undoes_an_old_fix(ctx):
    """Candidate drops the night rule that used to stop pl-old (an earlier fix)."""
    r = gates.g3_no_regression(cand(IRRELEVANT), ctx)
    assert not r.passed and r.evidence["regressed"] == ["pl-old"]


def test_g3_uses_regression_store(tmp_path, ctx, monkeypatch):
    from fa.verify import regression

    store = RegressionStore(tmp_path / "reg.json")
    store.add(attack("pl-stored"))
    monkeypatch.setattr(regression, "_default", store)
    del ctx["regression_plans"]
    r = gates.g3_no_regression(cand(IRRELEVANT), ctx)
    assert not r.passed and r.evidence["regressed"] == ["pl-stored"]


# ---------------------------------------------------------------- G4

def test_g4_accepts_when_most_variants_are_stopped(ctx):
    r = gates.g4_variants(cand(NIGHT), ctx)
    assert r.passed and r.evidence["rate"] == 1.0


def test_g4_rejects_overfitted_rule(ctx):
    """Stops only the exact failing plan: variants that happen at noon slip through."""
    ctx["variants"] = [attack(f"pl-v{i}", start=NOON + i * 600) for i in range(10)]
    r = gates.g4_variants(cand(NIGHT), ctx)
    assert not r.passed and r.evidence["rate"] == 0.0


def test_g4_records_actual_rate_at_the_threshold(ctx):
    ctx["variants"] = ([attack(f"n{i}", start=i * 600) for i in range(8)]
                       + [attack(f"d{i}", start=NOON + i * 600) for i in range(2)])
    r = gates.g4_variants(cand(NIGHT), ctx)
    assert r.passed and r.evidence["rate"] == pytest.approx(0.8)          # exactly at 80%
    ctx["variants"] = ctx["variants"][1:]                                  # 7 of 9 = 77.8%
    assert not gates.g4_variants(cand(NIGHT), ctx).passed


# ---------------------------------------------------------------- G5

def test_g5_accepts_narrow_rule(ctx):
    r = gates.g5_friction(cand(NIGHT), ctx)            # noon traffic: night rule never fires
    assert r.passed and r.evidence["cand_flagged"] == 0 and r.evidence["n"] == 3000


def test_g5_rejects_over_broad_rule(ctx):
    broad = mk_rule("R-all", "hold", ("hour_of_day", ">=", 0))
    r = gates.g5_friction(cand(broad), ctx)
    assert not r.passed and r.evidence["cand_rate"] == 1.0


def test_g5_rejects_rise_over_active_even_if_under_bound(ctx):
    """1% of 5000 payments flagged: Wilson upper (~1.3%) is under the 2% bound, but the
    rise over the active set (0%) is more than +0.5 pp, so G5 must still fail."""
    night_pay = lambda i: Event(event_id=f"x{i}", ts=3 * 3600 + i, type="payment", account=f"night{i}",  # noqa: E731
                                payee="shop", amount=1000, device="d1")
    ctx["normal_events"] = [noon_payment(i) for i in range(4950)] + [night_pay(i) for i in range(50)]
    r = gates.g5_friction(cand(NIGHT), ctx)
    assert r.evidence["cand_flagged"] == 50 and r.evidence["wilson_hi"] < 0.02
    assert not r.passed and "over active" in r.reason


def test_g5_falls_back_to_default_world_when_no_traffic(ctx, monkeypatch):
    """Real rounds pass only trace+plan: G5 must use M3's seeded world, not fail closed."""
    from fa.verify import shadow

    tiny = {"events": [], "bounds": {"validation": (0, 1)}}
    monkeypatch.setattr(shadow, "default_world", lambda: tiny)
    monkeypatch.setattr("fa.world.generator.events_in", lambda w, s: [noon_payment(i) for i in range(3000)])
    monkeypatch.setattr("fa.world.generator.warm_state", lambda w: shadow.fresh_state({}))
    del ctx["normal_events"]
    r = gates.g5_friction(cand(NIGHT), ctx)
    assert r.evidence["n"] == 3000 and r.passed


def test_g5_fails_closed_without_base(ctx):
    del ctx["base_rule_set"]
    assert gates.g5_friction(cand(NIGHT), ctx).reason.startswith("missing context")


# ---------------------------------------------------------------- G6

def test_g6_accepts_when_golden_cases_stay_allowed(ctx):
    r = gates.g6_golden(cand(NIGHT), ctx)
    assert r.passed and r.evidence["cases"] == 5


def test_g6_rejects_rule_that_blocks_rent_to_new_landlord(ctx):
    rent = Event(event_id="rent", ts=3 * 3600, type="payment", account="tenant", payee="new-landlord",
                 amount=2_000_000, device="d1")                           # 03:00 rent to a brand-new payee
    ctx["golden_cases"] = [[rent]]
    r = gates.g6_golden(cand(NIGHT), ctx)
    assert not r.passed and r.evidence["n_failures"] == 1


def test_g6_fails_closed_on_empty_set(ctx):
    ctx["golden_cases"] = []
    assert not gates.g6_golden(cand(NIGHT), ctx).passed


# ---------------------------------------------------------------- run_gates

def test_run_gates_all_green_for_good_patch(ctx):
    results = gates.run_gates(cand(NIGHT), ctx)
    assert [r.gate for r in results] == ["G1", "G2", "G3", "G4", "G5", "G6"]
    assert all(r.passed for r in results), [(r.gate, r.reason) for r in results if not r.passed]


def test_run_gates_skips_rest_when_g1_fails(ctx):
    bad = Rule.model_construct(id="R-bad", action="hold", rationale="", evidence={}, source="t", added_in="v2",
                               when=[Cond.model_construct(f="bogus", op=">", v=1.0)])
    results = gates.run_gates(cand(bad), ctx)
    assert [r.passed for r in results] == [False] * 6
    assert all("skipped" in r.reason for r in results[1:])


def test_run_gates_irrelevant_patch_fails_g2_g3_g4(ctx):
    results = {r.gate: r.passed for r in gates.run_gates(cand(IRRELEVANT), ctx)}
    assert results["G1"] and not results["G2"] and not results["G3"] and not results["G4"]
