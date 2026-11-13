"""Owner: M3. Seeded normal-traffic generation (customers' payments, logins,
recurring rent/bills, look-alikes). Called by fa.world.generator.build_world.

Per account and day:
- login on a known device with probability daily_login_prob
- Poisson(rate x weekend factor) payments, daytime-heavy hours,
  amount ~ LogNormal(log personal median, amount_sigma)
    * new_payee_share go to a brand-new payee (add_payee 1-15 min before)
    * the rest to a saved payee with Zipf-like preference
    * lookalike_share are replaced by an unusual-but-legitimate event
- recurring: monthly rent to a known landlord, monthly bills, weekly/monthly
  subscriptions

Look-alikes (tagged in labels, also used by golden.py):
    rent_new_landlord   add_payee + 8-15x mean payment to a brand-new landlord
    post_phone_change   login on a new phone, then a normal payment from it < 24 h later
    festival            5-10x mean to a known merchant
    new_supplier        business only: add_payee + 3-8x to a brand-new supplier
"""
from __future__ import annotations

import math

import numpy as np

from fa.core.clock import DAY, HOUR, MINUTE

HOUR_WEIGHTS = np.array([
    0.2, 0.1, 0.1, 0.1, 0.1, 0.3,     # 00-05
    0.8, 2.0, 3.5, 4.5, 5.0, 5.0,     # 06-11
    5.0, 5.0, 4.5, 4.5, 4.5, 5.0,     # 12-17
    5.5, 6.0, 5.5, 4.0, 2.5, 1.0,     # 18-23
])
HOUR_P = HOUR_WEIGHTS / HOUR_WEIGHTS.sum()
DAY_P = np.where(np.arange(24) >= 8, HOUR_WEIGHTS, 0.0)
DAY_P = DAY_P / DAY_P.sum()


def _ts(rng, day: int, daytime: bool = False) -> int:
    h = int(rng.choice(24, p=DAY_P if daytime else HOUR_P))
    return day * DAY + h * HOUR + int(rng.integers(HOUR))


def _amount(rng, median: float, sigma: float) -> int:
    return max(100, int(round(float(rng.lognormal(math.log(median), sigma)))))


def _u(rng, lo_hi) -> float:
    return float(rng.uniform(lo_hi[0], lo_hi[1]))


def generate_traffic(rng: np.random.Generator, profiles: dict, p: dict, n_days: int,
                     active_days: dict | None = None) -> tuple[list[dict], dict]:
    """Return (events sorted by ts with ids, labels {event_id: look-alike tag})."""
    active_days = active_days or {}
    sigma = float(p["amount_sigma"])
    horizon = n_days * DAY
    rec = p["recurring"]
    mix_names = list(p["lookalike_mix"])
    mix_w = np.array([p["lookalike_mix"][k] for k in mix_names], dtype=float)
    gap_lo, gap_hi = p["new_payee_gap_min"]
    wf = p["weekend_factor"]

    raw: list[tuple] = []
    seq = 0

    def emit(ts, aid, etype, amount=0, payee=None, device=None, channel="app", tag=None):
        nonlocal seq
        if 0 <= ts < min(horizon, active_days.get(aid, n_days) * DAY):
            raw.append((int(ts), aid, seq, etype, int(amount), payee, device, channel, tag))
            seq += 1

    for aid in profiles:                       # dict order = creation order: deterministic
        prof = profiles[aid]
        seg = prof["segment"]
        days = min(n_days, active_days.get(aid, n_days))
        channel = "netbanking" if seg == "business" else "upi"
        devices = list(prof["devices"])
        saved = list(prof["payees"])
        pref = np.array([1.0 / (i + 1) for i in range(len(saved))])
        pref /= pref.sum()
        merchants_saved = [x for x in saved if x.startswith("M-")] or saved
        mean = prof["mean"]
        n_new = 0
        new_phone_at: list[tuple[int, str]] = []   # (ts, device) phones added mid-run

        def device_at(ts):
            for t0, d in reversed(new_phone_at):
                if ts >= t0:
                    return d
            return devices[0] if len(devices) == 1 or rng.random() < 0.8 else devices[1]

        def new_payee(prefix):
            nonlocal n_new
            n_new += 1
            return f"{prefix}-{aid}-{n_new}"

        # recurring schedule (fixed days of month)
        has_rent = seg != "business" and rng.random() < rec["rent_prob"]
        rent_day = int(rng.integers(0, 5))
        rent_amt = int(prof["median"] * _u(rng, rec["rent_mult"]))
        landlord = f"L-{aid}"
        n_bills = int(rng.integers(rec["bills_per_month"][0], rec["bills_per_month"][1] + 1))
        bills = [(int(rng.integers(0, 28)), merchants_saved[int(rng.integers(len(merchants_saved)))],
                  int(prof["median"] * _u(rng, rec["bill_mult"]))) for _ in range(n_bills)]
        has_sub = rng.random() < rec["subscription_prob"]
        sub_dow = int(rng.integers(0, 7))
        sub_amt = max(100, int(prof["median"] * _u(rng, rec["subscription_mult"])))
        sub_merchant = merchants_saved[int(rng.integers(len(merchants_saved)))]

        for day in range(days):
            weekend = day % 7 in (5, 6)
            factor = (wf["business"] if seg == "business" else wf["retail"]) if weekend else 1.0

            if rng.random() < p["daily_login_prob"]:
                ts = _ts(rng, day)
                emit(ts, aid, "login", device=device_at(ts))

            # recurring
            if has_rent and day % 30 == rent_day:
                ts = _ts(rng, day, daytime=True)
                emit(ts, aid, "payment", rent_amt, landlord, device_at(ts), channel)
            for bday, biller, bamt in bills:
                if day % 30 == bday:
                    ts = _ts(rng, day, daytime=True)
                    emit(ts, aid, "payment", bamt, biller, device_at(ts), channel)
            if has_sub and day % 7 == sub_dow:
                ts = _ts(rng, day)
                emit(ts, aid, "payment", sub_amt, sub_merchant, device_at(ts), channel)

            for _ in range(int(rng.poisson(prof["rate"] * factor))):
                if rng.random() < p["lookalike_share"]:
                    w = mix_w * np.array([seg == "business" or k != "new_supplier"
                                          for k in mix_names])
                    kind = mix_names[int(rng.choice(len(mix_names), p=w / w.sum()))]
                    ts = _ts(rng, day, daytime=True)
                    if kind == "rent_new_landlord":
                        pay_ = new_payee("LN")
                        dev = device_at(ts)
                        emit(ts, aid, "add_payee", payee=pay_, device=dev, tag=kind)
                        emit(ts + int(rng.integers(2, 21)) * MINUTE, aid, "payment",
                             int(mean * _u(rng, (8, 15))), pay_, dev, channel, tag=kind)
                    elif kind == "post_phone_change":
                        dev = f"D-{aid}-n{len(new_phone_at)}"
                        new_phone_at.append((ts, dev))
                        emit(ts, aid, "login", device=dev, tag=kind)
                        pts = ts + int(rng.integers(1, 20)) * HOUR
                        emit(pts, aid, "payment", _amount(rng, prof["median"], sigma),
                             saved[int(rng.choice(len(saved), p=pref))], dev, channel, tag=kind)
                    elif kind == "festival":
                        emit(ts, aid, "payment", int(mean * _u(rng, (5, 10))),
                             merchants_saved[0], device_at(ts), channel, tag=kind)
                    else:  # new_supplier
                        pay_ = new_payee("S")
                        dev = device_at(ts)
                        emit(ts, aid, "add_payee", payee=pay_, device=dev, tag=kind)
                        emit(ts + int(rng.integers(5, 61)) * MINUTE, aid, "payment",
                             int(mean * _u(rng, (3, 8))), pay_, dev, channel, tag=kind)
                    continue

                ts = _ts(rng, day)
                amt = _amount(rng, prof["median"], sigma)
                dev = device_at(ts)
                if rng.random() < p["new_payee_share"]:
                    pay_ = new_payee("N")
                    add_ts = max(day * DAY, ts - int(rng.integers(gap_lo, gap_hi + 1)) * MINUTE)
                    emit(add_ts, aid, "add_payee", payee=pay_, device=dev)
                    emit(max(ts, add_ts + 1), aid, "payment", amt, pay_, dev, channel)
                else:
                    pay_ = saved[int(rng.choice(len(saved), p=pref))]
                    emit(ts, aid, "payment", amt, pay_, dev, channel)

    raw.sort(key=lambda r: (r[0], r[1], r[2]))
    events: list[dict] = []
    labels: dict[str, str] = {}
    for i, (ts, aid, _, etype, amount, payee, device, channel, tag) in enumerate(raw, start=1):
        eid = f"e-{i:07d}"
        events.append({"event_id": eid, "ts": ts, "type": etype, "account": aid,
                       "device": device, "payee": payee, "amount": amount, "channel": channel})
        if tag:
            labels[eid] = tag
    return events, labels


def generate_normal_events(rng: np.random.Generator, accounts: int, days: int) -> list[dict]:
    """Standalone helper (skeleton signature): ``accounts`` customers, ``days`` days of
    normal traffic as event dicts, other settings from params.yaml `world:`.
    No sandbox accounts. For the full world use generator.build_world()."""
    from fa.world.generator import load_params, make_profiles
    p = {**load_params(), "customers": int(accounts), "sandbox_victims": 0, "sandbox_mules": 0}
    profiles, _ = make_profiles(rng, p)
    events, _ = generate_traffic(rng, profiles, p, int(days))
    return events
