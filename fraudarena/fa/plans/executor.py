"""Owner: M1. execute(plan, state, rs) -> Trace (24h plan section 2.1 step 4).

Turns Plan.steps into Events, calls fa.core.engine.decide for each, and
computes loss_through / missed_step. Coded against M3's State/apply and
M4's engine.decide interfaces (docs/TIMELINE.md section 3) -- both are
still stubs owned by other roles; this module will raise NotImplementedError
at the engine.decide call until M4 lands it, same as a teammate's stub.
"""
from __future__ import annotations

from fa.contracts import Decision, Event, Plan, RuleSet, State, Step, Trace
from fa.core import engine

MULE_ACTS = {"cashout"}


def _event_type(act: str) -> str:
    return "payment" if act == "pay" else act


def _step_to_event(plan: Plan, step: Step, index: int) -> Event:
    return Event(
        event_id=f"{plan.plan_id}-s{index}",
        ts=step.t,
        type=_event_type(step.act),  # type: ignore[arg-type]
        account=step.actor,
        device=step.device,
        payee=step.payee,
        amount=step.amount or 0,
    )


def execute(plan: Plan, state: State, rs: RuleSet) -> Trace:
    steps_trace: list[tuple[Step, dict, Decision]] = []
    loss_through = 0
    missed_step: int | None = None

    for i, step in enumerate(plan.steps):
        event = _step_to_event(plan, step, i)
        features = {}  # filled in from decision.features once M3/M4 land; kept for shape
        decision = engine.decide(state, event, rs)
        steps_trace.append((step, features, decision))

        if decision.decision == "allow" and step.amount:
            if step.act in MULE_ACTS or step.actor == "mule":
                loss_through += step.amount
                if missed_step is None:
                    missed_step = i

    return Trace(plan_id=plan.plan_id, steps=steps_trace, loss_through=loss_through, missed_step=missed_step)
