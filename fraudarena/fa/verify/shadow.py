"""Owner: M4. Shadow run: candidate vs active rule set on the same traffic.

compare_on_events() replays events once, computing features once per event and
deciding with BOTH rule sets; state evolves under the ACTIVE set's decisions, so
the candidate is evaluated exactly as it would have been (nothing is applied for
it). Gate G5 and the Patch-review view both use this.

ctx keys (all optional, whatever is present is used):
  normal_events         iterable of event dicts/Events (validation traffic)
  normal_state_factory  () -> State to start the normal replay from
  world                 fa.world.generator.build_world() dict (derives the two above)
  state_factory         () -> State used for plan replays
  snapshot              fa.core.snapshot.take(state) result (used if no state_factory)
  regression_plans      list[Plan]; defaults to fa.verify.regression.all()
"""
from __future__ import annotations

from typing import Any, Callable, Iterable

from functools import lru_cache

from fa.contracts import RuleSet
from fa.core.engine import evaluate
from fa.core.features import compute_features
from fa.core.state import apply, as_event, new_state

MONEY_EVENTS = ("payment", "cashout")


def fresh_state(ctx: dict, key: str = "state_factory") -> Any:
    """A clean State from ctx: factory, else snapshot restore, else empty."""
    factory: Callable | None = ctx.get(key)
    if factory is not None:
        return factory()
    if ctx.get("snapshot") is not None:
        from fa.core.snapshot import restore

        return restore(ctx["snapshot"])
    from fa.world.generator import sandbox_state

    return sandbox_state()


@lru_cache(maxsize=1)
def default_world() -> dict:
    """M3's seeded world (built once per process). Used when ctx supplies no traffic."""
    from fa.world.generator import build_world

    return build_world()


def normal_traffic(ctx: dict) -> tuple[Iterable[Any], Callable[[], Any]] | None:
    """(events, state_factory) for normal validation traffic, or None if not supplied."""
    if ctx.get("normal_events") is not None:
        factory = ctx.get("normal_state_factory") or (lambda: fresh_state(ctx))
        return ctx["normal_events"], factory
    world = ctx.get("world")
    if world is None:
        world = default_world()       # real rounds pass only trace+plan: use M3's seeded world
    if world is not None:
        from fa.world.generator import events_in, warm_state

        return events_in(world, "validation"), (lambda: warm_state(world))
    return None


def compare_on_events(
    events: Iterable[Any], state: Any, active: RuleSet, candidate: RuleSet, max_examples: int = 5
) -> dict:
    """One replay: counts of money events flagged (hold or block) by each set."""
    n = base_flagged = cand_flagged = 0
    new_flags: list[dict] = []
    new_count = lost_flags = 0
    for ev in events:
        feats = compute_features(state, ev)
        a_action, _ = evaluate(feats, active.rules)
        c_action, c_fired = evaluate(feats, candidate.rules)
        e = as_event(ev)
        if e["type"] in MONEY_EVENTS:
            n += 1
            a_flag, c_flag = a_action != "allow", c_action != "allow"
            base_flagged += a_flag
            cand_flagged += c_flag
            if c_flag and not a_flag:
                new_count += 1
                if len(new_flags) < max_examples:
                    new_flags.append({"event_id": e["event_id"], "account": e["account"],
                                      "amount": e["amount"], "action": c_action, "fired": c_fired})
            elif a_flag and not c_flag:
                lost_flags += 1
        apply(state, ev, a_action)
    return {
        "n": n,
        "base_flagged": base_flagged,
        "cand_flagged": cand_flagged,
        "new_flags": new_count,
        "lost_flags": lost_flags,
        "base_rate": base_flagged / n if n else 0.0,
        "cand_rate": cand_flagged / n if n else 0.0,
        "examples": new_flags,
    }


def compare_plans(plans: Iterable[Any], active: RuleSet, candidate: RuleSet, ctx: dict) -> dict:
    """Replay attack plans under both sets; a lost catch is a plan the active set
    stopped (loss 0) that the candidate lets through (loss > 0)."""
    from fa.plans.executor import execute

    rows = []
    lost = []
    for plan in plans:
        a = execute(plan, fresh_state(ctx), active).loss_through
        c = execute(plan, fresh_state(ctx), candidate).loss_through
        rows.append({"plan_id": plan.plan_id, "loss_active": a, "loss_candidate": c})
        if a == 0 and c > 0:
            lost.append(plan.plan_id)
    return {"checked": len(rows), "lost_catches": lost, "plans": rows}


def compare(active: RuleSet, candidate: RuleSet, ctx: dict | None = None) -> dict:
    """Shadow report for the Patch-review view. Informational: G5 and G3 enforce."""
    ctx = ctx or {}
    out: dict = {"active": active.version, "candidate": candidate.version, "normal": None, "regression": None}
    traffic = normal_traffic(ctx)
    if traffic is not None:
        events, factory = traffic
        out["normal"] = compare_on_events(events, factory(), active, candidate)
    plans = ctx.get("regression_plans")
    if plans is None:
        from fa.verify import regression

        plans = regression.all()
    out["regression"] = compare_plans(plans, active, candidate, ctx)
    return out
