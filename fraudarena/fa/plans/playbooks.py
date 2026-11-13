"""Owner: M1. Playbook parameter ranges and build_plan (24h plan section 7).

P1 takeover and drain: new-device login, add payee, small test payment,
wait, large payment (optionally split), cash-out.
P2 mule chain: victim pays mule 1, then mule 2, ..., then cash-out, with
splits and delays per hop.
P3 structuring: many payments just under a limit, across payees and time.
"""
from __future__ import annotations

from fa.contracts import Plan, Playbook, Step

DEFAULT_VICTIM_MEAN_AMOUNT = 100_00  # paise; overridable via params["victim_mean_amount"]

# (low, high) inclusive searchable ranges, per 24h plan section 7.
PARAM_RANGES: dict[Playbook, dict[str, tuple[float, float]]] = {
    "P1": {
        "test_amt": (1, 500),
        "wait_s": (60, 43_200),
        "drain_mult": (3, 60),
        "splits": (1, 6),
        "split_gap_s": (30, 7_200),
        "device_age_h": (0, 12),
    },
    "P2": {
        "hops": (1, 3),
        "split_k": (1, 4),
        "hop_delay_s": (30, 21_600),
        "amount_mult": (3, 40),
    },
    "P3": {
        "size_frac": (0.6, 0.99),
        "n_payees": (1, 8),
        "spacing_s": (60, 14_400),
        "n_payments": (3, 12),
    },
}

STRUCTURING_LIMIT_PAISE = 50_000_00  # L, per 24h plan section 7 (illustrative)


def _build_p1(plan_id: str, params: dict, seed: int) -> list[Step]:
    victim_mean = params.get("victim_mean_amount", DEFAULT_VICTIM_MEAN_AMOUNT)
    test_amt = int(params["test_amt"])
    wait_s = int(params["wait_s"])
    drain_mult = params["drain_mult"]
    splits = max(1, int(params["splits"]))
    split_gap_s = int(params["split_gap_s"])

    total_drain = int(victim_mean * drain_mult)
    per_split = total_drain // splits

    steps: list[Step] = [
        Step(t=0, actor="victim", act="login", device="new"),
        Step(t=180, actor="victim", act="add_payee", payee="mule"),
        Step(t=480, actor="victim", act="pay", payee="mule", amount=test_amt),
    ]
    t = 480 + wait_s
    for i in range(splits):
        amount = per_split if i < splits - 1 else total_drain - per_split * (splits - 1)
        steps.append(Step(t=t, actor="victim", act="pay", payee="mule", amount=amount))
        t += split_gap_s
    steps.append(Step(t=t + 60, actor="mule", act="cashout", amount=total_drain))
    return steps


def _build_p2(plan_id: str, params: dict, seed: int) -> list[Step]:
    victim_mean = params.get("victim_mean_amount", DEFAULT_VICTIM_MEAN_AMOUNT)
    hops = max(1, int(params["hops"]))
    split_k = max(1, int(params["split_k"]))
    hop_delay_s = int(params["hop_delay_s"])
    amount_mult = params["amount_mult"]

    total = int(victim_mean * amount_mult)
    per_split = total // split_k

    steps: list[Step] = [Step(t=0, actor="victim", act="login", device="new")]
    t = 60
    mule_name = "mule1"
    steps.append(Step(t=t, actor="victim", act="add_payee", payee=mule_name))
    t += 60
    for i in range(split_k):
        amount = per_split if i < split_k - 1 else total - per_split * (split_k - 1)
        steps.append(Step(t=t, actor="victim", act="pay", payee=mule_name, amount=amount))
        t += 30
    for hop in range(2, hops + 1):
        t += hop_delay_s
        next_mule = f"mule{hop}"
        steps.append(Step(t=t, actor="mule", act="pay", payee=next_mule, amount=total))
    t += hop_delay_s
    steps.append(Step(t=t, actor="mule", act="cashout", amount=total))
    return steps


def _build_p3(plan_id: str, params: dict, seed: int) -> list[Step]:
    limit = params.get("structuring_limit", STRUCTURING_LIMIT_PAISE)
    size_frac = params["size_frac"]
    n_payees = max(1, int(params["n_payees"]))
    spacing_s = int(params["spacing_s"])
    n_payments = max(1, int(params["n_payments"]))

    amount = int(limit * size_frac)
    steps: list[Step] = [Step(t=0, actor="victim", act="login", device="new")]
    t = 60
    for i in range(n_payments):
        payee = f"payee{(i % n_payees) + 1}"
        if i < n_payees:
            steps.append(Step(t=t, actor="victim", act="add_payee", payee=payee))
            t += 30
        steps.append(Step(t=t, actor="victim", act="pay", payee=payee, amount=amount))
        t += spacing_s
    # MAX_STEPS safety net: keep the cash-out (the only step that realises loss) as step 12.
    paid = steps[:11]
    total = sum(s.amount or 0 for s in paid if s.act == "pay")
    paid.append(Step(t=paid[-1].t + 60, actor="mule", act="cashout", amount=total))
    return paid


_BUILDERS = {"P1": _build_p1, "P2": _build_p2, "P3": _build_p3}


def build_plan(playbook: Playbook, params: dict, seed: int) -> Plan:
    plan_id = f"pl-{playbook}-{seed}"
    steps = _BUILDERS[playbook](plan_id, params, seed)
    return Plan(plan_id=plan_id, playbook=playbook, seed=seed, params=params, steps=steps)
