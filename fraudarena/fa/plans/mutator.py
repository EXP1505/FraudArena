"""Owner: M1. variants(plan, n, seed) -> list[Plan], used by gate G4.

Deterministic mutation operators (24h plan section 7), applied with
held-out seeds: scale amount by 0.5-1.5x, shift waits by 0.5-2x, split a
payment into 2-4 parts, swap which payee, change device age, insert 1-3
decoy normal payments. Every variant must still pass
fa.plans.validator.validate().
"""
from __future__ import annotations

import random

from fa.contracts import Plan, Step
from fa.plans.schema import MAX_STEPS

_OPERATORS = ("scale_amount", "shift_waits", "split_payment", "swap_payee", "insert_decoy")


def _scale_amount(steps: list[Step], rng: random.Random) -> list[Step]:
    factor = rng.uniform(0.5, 1.5)
    return [
        s.model_copy(update={"amount": int(s.amount * factor)}) if s.amount else s
        for s in steps
    ]


def _shift_waits(steps: list[Step], rng: random.Random) -> list[Step]:
    factor = rng.uniform(0.5, 2.0)
    base_t = steps[0].t
    out = []
    for s in steps:
        new_t = base_t + int((s.t - base_t) * factor)
        out.append(s.model_copy(update={"t": max(0, new_t)}))
    return out


def _split_payment(steps: list[Step], rng: random.Random) -> list[Step]:
    pay_idx = [i for i, s in enumerate(steps) if s.amount and s.act in ("pay", "payment")]
    if not pay_idx or len(steps) >= MAX_STEPS:
        return steps
    i = rng.choice(pay_idx)
    step = steps[i]
    parts = rng.randint(2, 4)
    per = step.amount // parts
    new_steps = [
        step.model_copy(update={"amount": per if j < parts - 1 else step.amount - per * (parts - 1),
                                 "t": step.t + j * 30})
        for j in range(parts)
    ]
    out = steps[:i] + new_steps + steps[i + 1:]
    return out[:MAX_STEPS]


def _swap_payee(steps: list[Step], rng: random.Random) -> list[Step]:
    payees = sorted({s.payee for s in steps if s.payee})
    if len(payees) < 1:
        return steps
    swap_to = f"{rng.choice(payees)}-alt"
    idx = [i for i, s in enumerate(steps) if s.payee]
    if not idx:
        return steps
    i = rng.choice(idx)
    out = list(steps)
    out[i] = out[i].model_copy(update={"payee": swap_to})
    return out


def _insert_decoy(steps: list[Step], rng: random.Random) -> list[Step]:
    if len(steps) >= MAX_STEPS:
        return steps
    n = rng.randint(1, min(3, MAX_STEPS - len(steps)))
    out = list(steps)
    last_t = out[-1].t
    for _ in range(n):
        last_t += rng.randint(60, 600)
        out.insert(-1, Step(t=last_t, actor="victim", act="pay", payee="regular", amount=rng.randint(1, 50)))
    out.sort(key=lambda s: s.t)
    return out[:MAX_STEPS]


_OP_FUNCS = {
    "scale_amount": _scale_amount,
    "shift_waits": _shift_waits,
    "split_payment": _split_payment,
    "swap_payee": _swap_payee,
    "insert_decoy": _insert_decoy,
}


def variants(plan: Plan, n: int, seed: int) -> list[Plan]:
    out: list[Plan] = []
    for i in range(n):
        rng = random.Random(f"{seed}:{i}")
        op = rng.choice(_OPERATORS)
        new_steps = _OP_FUNCS[op](list(plan.steps), rng)
        out.append(
            Plan(
                plan_id=f"{plan.plan_id}-var{i}",
                playbook=plan.playbook,
                seed=plan.seed,
                params=plan.params,
                steps=new_steps,
            )
        )
    return out
