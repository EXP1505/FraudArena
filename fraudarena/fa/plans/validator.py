"""Owner: M1. validate(plan) -> list[str]; empty list means valid.

Checks the caps from fa.plans.schema: sandbox roles only, at most
MAX_STEPS steps, span at most MAX_SPAN_SECONDS, and total paid amount at
most MAX_TOTAL_VS_VICTIM_MEAN x the victim's mean payment (if known).
"""
from __future__ import annotations

from fa.contracts import Plan
from fa.plans.schema import (
    ALLOWED_ACTS,
    MAX_SPAN_SECONDS,
    MAX_STEPS,
    MAX_TOTAL_VS_VICTIM_MEAN,
    SANDBOX_ACTORS,
)


def validate(plan: Plan) -> list[str]:
    """Return a list of human-readable violations; [] means the plan is valid."""
    violations: list[str] = []

    if not plan.steps:
        violations.append("plan has no steps")
        return violations

    if len(plan.steps) > MAX_STEPS:
        violations.append(f"{len(plan.steps)} steps exceeds MAX_STEPS={MAX_STEPS}")

    for i, step in enumerate(plan.steps):
        if step.actor not in SANDBOX_ACTORS:
            violations.append(f"step {i}: actor {step.actor!r} is not a sandbox role")
        if step.act not in ALLOWED_ACTS:
            violations.append(f"step {i}: unknown act {step.act!r}")
        if step.t < 0:
            violations.append(f"step {i}: negative t={step.t}")

    ts = [s.t for s in plan.steps]
    span = max(ts) - min(ts)
    if span > MAX_SPAN_SECONDS:
        violations.append(f"span {span}s exceeds MAX_SPAN_SECONDS={MAX_SPAN_SECONDS}")

    total_amount = sum(s.amount or 0 for s in plan.steps)
    victim_mean = plan.params.get("victim_mean_amount")
    if victim_mean:
        cap = MAX_TOTAL_VS_VICTIM_MEAN * victim_mean
        if total_amount > cap:
            violations.append(
                f"total amount {total_amount} exceeds {MAX_TOTAL_VS_VICTIM_MEAN}x "
                f"victim mean ({cap})"
            )

    return violations
