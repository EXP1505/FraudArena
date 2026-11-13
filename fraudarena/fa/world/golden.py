"""Owner: M3. golden_cases() -> list[list[Event]]: 200 benign-but-unusual
cases (rent to new landlord, pay after phone change, festival 5-10x, new
supplier). Used by M4's gate G6 — every case must stay allowed by v1.

Each case is self-contained (G6 replays it on an empty state): a few weeks of
ordinary payments build the account's profile, then the unusual-but-legitimate
event(s) follow. Deterministic: same params -> same cases. Cases are built to
look like the look-alikes in the world generator, but with the human context
that makes them clearly benign (payee added well in advance, daytime, moderate
size), so a patch that blocks them is over-broad.
"""
from __future__ import annotations

import numpy as np

from fa.config import load_config
from fa.contracts import Event
from fa.core.clock import DAY, HOUR

KINDS = ("rent_new_landlord", "post_phone_change", "festival", "new_supplier")


def golden_cases(n: int | None = None, seed: int | None = None) -> list[list[Event]]:
    cfg = load_config()
    wp = cfg.section("world")
    n = int(n if n is not None else wp["golden_cases"])
    seed = int(seed if seed is not None else cfg.section("common").get("seed", 42))
    rng = np.random.default_rng(seed + 1_000_003)   # separate stream from the world
    base_pay = int(cfg.section("ml").get("export", {}).get("victim_payment_paise", 10_000))
    cases: list[list[Event]] = []
    for i in range(n):
        kind = KINDS[i % len(KINDS)]
        cases.append(_case(rng, i, kind, base_pay))
    return cases


def _case(rng: np.random.Generator, i: int, kind: str, base_pay: int) -> list[Event]:
    acc, dev, new_dev = f"G-{i:03d}", f"D-G-{i:03d}-0", f"D-G-{i:03d}-1"
    median = int(base_pay * rng.uniform(5, 40))
    evs: list[Event] = []

    def add(ts, type, amount=0, payee=None, device=dev):
        evs.append(Event(event_id=f"g{i:03d}-{len(evs):02d}", ts=int(ts), type=type, account=acc,
                         device=device, payee=payee, amount=int(amount), channel="upi"))

    t0 = 9 * HOUR   # setup events happen in the daytime, like a customer's first session
    add(t0, "login")
    add(t0 + 60, "add_payee", payee="P-usual")
    # 3 weeks of one daytime payment per day at about the personal median
    for d in range(1, 22):
        amt = median * float(np.clip(rng.lognormal(0, 0.25), 0.6, 1.6))
        add(d * DAY + int(rng.integers(10, 18)) * HOUR + int(rng.integers(0, 3600)), "payment", amt, "P-usual")
    day = 23
    hour = int(rng.integers(10, 17)) * HOUR + int(rng.integers(0, 3600))
    t = day * DAY + hour
    if kind == "rent_new_landlord":
        # landlord added the evening before, paid next day; rent a few times the median
        add(t - 20 * HOUR, "add_payee", payee="P-landlord")
        add(t, "payment", median * rng.uniform(3, 4.5), "P-landlord")
    elif kind == "post_phone_change":
        # new phone logged in the day before; ordinary payment, nothing else in the hour
        add(t - 18 * HOUR, "login", device=new_dev)
        add(t, "payment", median * rng.uniform(0.6, 1.6), "P-usual", device=new_dev)
    elif kind == "festival":
        add(t, "payment", median * rng.uniform(3, 4.5), "P-usual")
    else:  # new_supplier
        add(t - 26 * HOUR, "add_payee", payee="P-supplier")
        add(t, "payment", median * rng.uniform(3, 4.5), "P-supplier")
    evs.sort(key=lambda e: e.ts)
    return evs
