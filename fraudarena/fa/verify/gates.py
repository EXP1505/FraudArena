"""Owner: M4. Gates G1 to G6 (24h plan section 11). Pure, deterministic, no LLM.

    gate(candidate: RuleSet, ctx: dict) -> GateResult

`candidate` is the FULL candidate rule set (active rules + the proposed rule).
Gates fail closed: if the context a gate needs is missing, it FAILS with reason
"missing context: ..." -- it never passes by absence.

ctx keys
  base_rule_set    RuleSet currently active (G1, G5; defaults: all rules treated as new)
  plan             Plan of the failing attack (G2, G4)
  trace            Trace of that attack (informational)
  state_factory    () -> State to replay plans from (or `snapshot`)
  regression_plans list[Plan] (G3; default fa.verify.regression.all())
  variants         list[Plan] (G4; default fa.plans.mutator.variants(plan, n, seed))
  variant_seed     int for the default variants (default 9001, held out from search)
  normal_events / normal_state_factory / world   validation traffic (G5), see shadow.py
  golden_cases     list[list[Event]] (G6; default fa.world.golden.golden_cases())
"""
from __future__ import annotations

from typing import Any, Callable

from fa.config import load_config
from fa.contracts import FEATURES, MAX_CONDITIONS, GateResult, Rule, RuleSet
from fa.core.engine import evaluate
from fa.core.features import compute_features
from fa.core.state import apply
from fa.verify.shadow import MONEY_EVENTS, compare_on_events, fresh_state, normal_traffic
from fa.verify.wilson import wilson_interval

ALLOWED_OPS = ("<", "<=", ">", ">=", "==")


def _ok(gate: str, reason: str = "", **evidence: Any) -> GateResult:
    return GateResult(gate=gate, passed=True, reason=reason, evidence=evidence)  # type: ignore[arg-type]


def _fail(gate: str, reason: str, **evidence: Any) -> GateResult:
    return GateResult(gate=gate, passed=False, reason=reason, evidence=evidence)  # type: ignore[arg-type]


def _missing(gate: str, what: str) -> GateResult:
    return _fail(gate, f"missing context: {what}")


def _signature(rule: Rule) -> tuple:
    return rule.action, frozenset((c.f, c.op, float(c.v)) for c in rule.when)


# ----------------------------------------------------------------------- G1

def g1_valid(candidate: RuleSet, ctx: dict) -> GateResult:
    """Schema passes; features in the allowed list; operators allowed; at most 4
    conditions; not identical to an existing rule; ids unique."""
    base: RuleSet | None = ctx.get("base_rule_set")
    base_ids = {r.id for r in base.rules} if base else set()
    new_rules = [r for r in candidate.rules if r.id not in base_ids] if base else list(candidate.rules)
    if base is not None and not new_rules:
        return _fail("G1", "candidate adds no new rule")

    problems: list[str] = []
    ids = [r.id for r in candidate.rules]
    for i in sorted({i for i in ids if ids.count(i) > 1}):
        problems.append(f"duplicate rule id {i}")

    existing = {_signature(r): r.id for r in (base.rules if base else [])}
    seen_new: dict[tuple, str] = {}
    for r in new_rules:
        try:
            Rule.model_validate(r.model_dump())
        except Exception as exc:  # pydantic ValidationError and friends
            problems.append(f"{r.id}: schema invalid ({str(exc).splitlines()[0]})")
        if not 1 <= len(r.when) <= MAX_CONDITIONS:
            problems.append(f"{r.id}: {len(r.when)} conditions (allowed 1..{MAX_CONDITIONS})")
        for c in r.when:
            if c.f not in FEATURES:
                problems.append(f"{r.id}: unknown feature {c.f!r}")
            if c.op not in ALLOWED_OPS:
                problems.append(f"{r.id}: operator {c.op!r} not allowed")
        if r.action not in ("hold", "block"):
            problems.append(f"{r.id}: action {r.action!r} not allowed")
        sig = _signature(r)
        if sig in existing:
            problems.append(f"{r.id}: identical to existing rule {existing[sig]}")
        elif sig in seen_new:
            problems.append(f"{r.id}: identical to new rule {seen_new[sig]}")
        seen_new[sig] = r.id

    if problems:
        return _fail("G1", "; ".join(problems), problems=problems, checked=[r.id for r in new_rules])
    return _ok("G1", f"{len(new_rules)} new rule(s) valid", checked=[r.id for r in new_rules])


# ----------------------------------------------------------------------- G2

def _first_cashout_index(plan) -> int | None:
    for i, s in enumerate(plan.steps):
        if s.act == "cashout":
            return i
    return None


def g2_stops_attack(candidate: RuleSet, ctx: dict) -> GateResult:
    """Replay the failing plan (same seed): loss through = 0 and the decision at
    or before the cash-out is hold or block."""
    plan = ctx.get("plan")
    if plan is None:
        return _missing("G2", "plan")
    from fa.plans.executor import execute

    trace = execute(plan, fresh_state(ctx), candidate)
    decisions = [d.decision for (_s, _f, d) in trace.steps]
    cash = _first_cashout_index(plan)
    upto = decisions if cash is None else decisions[: cash + 1]
    flagged_in_time = any(d != "allow" for d in upto)
    evidence = {"plan_id": plan.plan_id, "loss_through": trace.loss_through,
                "decisions": decisions, "cashout_index": cash}
    if trace.loss_through != 0:
        return _fail("G2", f"attack still extracts {trace.loss_through}", **evidence)
    if not flagged_in_time:
        return _fail("G2", "no hold/block at or before the cash-out", **evidence)
    return _ok("G2", "failing attack stopped", **evidence)


# ----------------------------------------------------------------------- G3

def g3_no_regression(candidate: RuleSet, ctx: dict) -> GateResult:
    """Every plan in the regression set (all earlier lossy plans) still has loss 0."""
    plans = ctx.get("regression_plans")
    if plans is None:
        from fa.verify import regression

        plans = regression.all()
    from fa.plans.executor import execute

    rows, regressed = [], []
    for p in plans:
        loss = execute(p, fresh_state(ctx), candidate).loss_through
        rows.append({"plan_id": p.plan_id, "loss_through": loss})
        if loss > 0:
            regressed.append(p.plan_id)
    if regressed:
        return _fail("G3", f"{len(regressed)} earlier attack(s) succeed again: {regressed}",
                     plans=rows, regressed=regressed)
    return _ok("G3", f"{len(rows)} regression plan(s) still stopped", plans=rows)


# ----------------------------------------------------------------------- G4

def g4_variants(candidate: RuleSet, ctx: dict) -> GateResult:
    """Mutated variants of the failing plan (held-out seeds): at least
    verifier.variants_pass_rate of them have loss 0. The actual rate is recorded."""
    cfg = load_config().section("verifier")
    need = float(cfg.get("variants_pass_rate", 0.80))
    variants = ctx.get("variants")
    if variants is None:
        plan = ctx.get("plan")
        if plan is None:
            return _missing("G4", "plan or variants")
        from fa.plans.mutator import variants as make_variants

        variants = make_variants(plan, int(cfg.get("variants_n", 50)), int(ctx.get("variant_seed", 9001)))
    if not variants:
        return _fail("G4", "no variants to evaluate")
    from fa.plans.executor import execute

    results = [{"plan_id": v.plan_id, "loss_through": execute(v, fresh_state(ctx), candidate).loss_through}
               for v in variants]
    stopped = sum(1 for r in results if r["loss_through"] == 0)
    rate = stopped / len(results)
    evidence = {"n": len(results), "stopped": stopped, "rate": rate, "required": need, "variants": results}
    if rate < need:
        return _fail("G4", f"only {rate:.0%} of {len(results)} variants stopped (need {need:.0%})", **evidence)
    return _ok("G4", f"{rate:.0%} of {len(results)} variants stopped", **evidence)


# ----------------------------------------------------------------------- G5

def g5_friction(candidate: RuleSet, ctx: dict) -> GateResult:
    """Replay validation normal traffic: Wilson 95% upper bound of the hold+block
    rate <= verifier.friction_upper_bound AND at most verifier.friction_upper_delta
    above the active set."""
    cfg = load_config().section("verifier")
    bound = float(cfg.get("friction_upper_bound", 0.02))
    delta = float(cfg.get("friction_upper_delta", 0.005))
    base: RuleSet | None = ctx.get("base_rule_set")
    if base is None:
        return _missing("G5", "base_rule_set")
    traffic = normal_traffic(ctx)
    if traffic is None:
        return _missing("G5", "normal_events or world")
    events, factory = traffic
    r = compare_on_events(events, factory(), base, candidate)
    if r["n"] == 0:
        return _fail("G5", "no normal payments in validation traffic", **r)
    lo, hi = wilson_interval(r["cand_flagged"], r["n"])
    evidence = {**r, "wilson_lo": lo, "wilson_hi": hi, "bound": bound, "delta": delta}
    if hi > bound:
        return _fail("G5", f"hold+block rate {r['cand_rate']:.2%}, Wilson upper {hi:.2%} > {bound:.2%}", **evidence)
    if r["cand_rate"] - r["base_rate"] > delta:
        return _fail("G5", f"rate rises {r['cand_rate'] - r['base_rate']:.2%} (> {delta:.2%}) over active set", **evidence)
    return _ok("G5", f"hold+block {r['cand_rate']:.2%}, Wilson upper {hi:.2%}", **evidence)


# ----------------------------------------------------------------------- G6

def g6_golden(candidate: RuleSet, ctx: dict) -> GateResult:
    """Curated benign-but-unusual cases: every event of every case stays allowed."""
    cases = ctx.get("golden_cases")
    if cases is None:
        try:
            from fa.world.golden import golden_cases

            cases = golden_cases()
        except NotImplementedError:
            return _missing("G6", "golden_cases (fa.world.golden not implemented yet)")
    if not cases:
        return _fail("G6", "golden set is empty")

    failures = []
    for i, case in enumerate(cases):
        state = fresh_state(ctx)
        for ev in case:
            feats = compute_features(state, ev)
            action, fired = evaluate(feats, candidate.rules)
            if action != "allow":
                failures.append({"case": i, "event_id": getattr(ev, "event_id", None),
                                 "action": action, "fired": fired})
            apply(state, ev, action)
    evidence = {"cases": len(cases), "failures": failures[:20], "n_failures": len(failures)}
    if failures:
        return _fail("G6", f"{len(failures)} golden event(s) no longer allowed", **evidence)
    return _ok("G6", f"all {len(cases)} golden cases still allowed", **evidence)


GATES: tuple[Callable[[RuleSet, dict], GateResult], ...] = (
    g1_valid, g2_stops_attack, g3_no_regression, g4_variants, g5_friction, g6_golden,
)


def run_gates(candidate: RuleSet, ctx: dict) -> list[GateResult]:
    """Run G1..G6 in order. If G1 fails, the later gates are not run (they would
    execute an invalid rule); they are reported as failed with reason 'skipped'."""
    results: list[GateResult] = []
    g1 = g1_valid(candidate, ctx)
    results.append(g1)
    for gate in GATES[1:]:
        if not g1.passed:
            results.append(_fail(gate.__name__[:2].upper(), "skipped: G1 failed"))
        else:
            results.append(gate(candidate, ctx))
    return results
