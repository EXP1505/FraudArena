"""Owner: M1. execute(plan, state, rs) -> Trace (24h plan section 2.1 step 4).

Turns Plan.steps into Events, calls fa.core.engine.decide_with_features for
each (so the trace carries the real per-step features M3/M4 compute), and
computes loss_through / missed_step (24h plan section 5.2: "Loss through =
total fraudulent amount that was allowed and reached a mule account or
cash-out"). Money passing victim -> mule -> cash-out is the same rupee
counted once, at the point it leaves the system for good: an allowed
"cashout" step. Earlier "pay" hops into the mule chain do not add to the
total themselves (they would double-count the cash-out), but they are
still where the fraud could have been stopped, so missed_step is the index
of the first allowed money-moving step ("pay"/"payment"/"cashout"), not
necessarily the cash-out itself.
"""
from __future__ import annotations

from fa.contracts import Decision, Event, Plan, RuleSet, State, Step, Trace
from fa.core import engine

MONEY_ACTS = {"pay", "payment", "cashout"}
TERMINAL_ACTS = {"cashout"}


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
        decision, features = engine.decide_with_features(state, event, rs, commit=True)
        steps_trace.append((step, features, decision))

        if decision.decision == "allow" and step.amount and step.act in MONEY_ACTS:
            if missed_step is None:
                missed_step = i
            if step.act in TERMINAL_ACTS:
                loss_through += step.amount

    return Trace(plan_id=plan.plan_id, steps=steps_trace, loss_through=loss_through, missed_step=missed_step)
