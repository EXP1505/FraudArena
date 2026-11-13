"""Owner: M3. compute_features(state, ev) -> dict[str, float]: the agreed
features (fa.contracts.FEATURES, in that order), computed from state BEFORE ev is
applied. Definitions: 24h plan section 5.1. Shared by the engine, the world replay
and the ML export.

Call order is always:   f = compute_features(state, ev);  apply(state, ev, decision)

Leakage rule: computed from state *before* the event is applied, and every lookup
reads only entries strictly earlier than the event (ts < t). So a state that already
contains this event or later ones cannot leak them (test_features: no-leakage test).
Consequence: two events in the same simulated second do not see each other.

Windows: "last 1 h" means t - 3600 < ts < t.
"""
from __future__ import annotations

from typing import Any

from fa.contracts import FEATURES, State

from .clock import DAY, HOUR, hour_of_day
from .state import MIN_PAYS_FOR_AVG, PAY_WINDOW_S, as_event, window

# Computed but only returned if listed in contracts.FEATURES (M1 owns that list).
EXTRA_FEATURES = ("device_age_h",)

NIGHT_END_H = 5                 # night_flag: 00:00 <= time < 05:00
NEW_AGE_S = DAY                 # "young" payee / "changed" device: first seen < 24 h ago


_EMPTY: dict = {}
_NONE: list = []


def compute_features(state: State, ev: Any) -> dict[str, float]:
    """Return {feature: number} for ``ev`` from ``state`` before ``ev`` is applied."""
    e = as_event(ev)
    t = e["ts"]
    amount = float(e["amount"])
    acc = state.accounts.get(e["account"])
    payees = acc.payees if acc is not None else _EMPTY
    devices = acc.devices if acc is not None else _EMPTY
    recent = acc.recent_pays if acc is not None else _NONE
    inflows_all = getattr(state, "inflows", _EMPTY)
    t_1h, t_24h = t - HOUR, t - DAY

    # -- sender's payment history in (t - 30 d, t)
    n_30d = 0
    sum_30d = 0.0
    n_1h = n_24h = 0
    s_1h = s_24h = s_new_1h = 0.0
    payees_1h = set()
    for (pts, pamt, ppayee) in window(recent, t - PAY_WINDOW_S, t):
        n_30d += 1
        sum_30d += pamt
        if pts > t_24h:
            n_24h += 1
            s_24h += pamt
            if pts > t_1h:
                n_1h += 1
                s_1h += pamt
                payees_1h.add(ppayee)
                first = payees.get(ppayee)
                if first is None or first >= t or t - first < NEW_AGE_S:
                    s_new_1h += pamt

    # -- amount_ratio_30d: amount / 30-day mean; 1.0 if fewer than 3 payments
    if n_30d >= MIN_PAYS_FOR_AVG and sum_30d > 0:
        ratio = amount / (sum_30d / n_30d)
    else:
        ratio = 1.0

    # -- payee_age_h: 0 if new / unknown / the event is the add
    payee = e["payee"]
    p_first = payees.get(payee) if payee else None
    payee_age_h = (t - p_first) / HOUR if (p_first is not None and p_first < t) else 0.0

    # -- device_age_h / device_changed_24h: about the device in use
    dev = e["device"]
    if dev:
        d_first = devices.get(dev)
        device_age_h = (t - d_first) / HOUR if (d_first is not None and d_first < t) else 0.0
        device_changed = 1 if device_age_h * HOUR < NEW_AGE_S else 0
    else:
        device_age_h = 0.0
        device_changed = 0

    # -- receiving side. Recipient = payee for a payment; for a cashout the account
    #    itself is the one passing money through.
    recipient = e["account"] if e["type"] == "cashout" else payee
    fan_in = 0
    passthrough = 0.0
    if recipient:
        senders = set()
        in_1h = 0.0
        for (its, isender, iamt) in window(inflows_all.get(recipient, _NONE), t_24h, t):
            senders.add(isender)
            if its > t_1h:
                in_1h += iamt
        fan_in = len(senders)
        if in_1h > 0:
            racc = state.accounts.get(recipient)
            out_1h = 0.0
            if racc is not None:
                for (_, oamt) in window(getattr(racc, "outflows", _NONE), t_1h, t):
                    out_1h += oamt
            passthrough = out_1h / in_1h

    h = hour_of_day(t)
    values = {
        "amount_ratio_30d": ratio,
        "payee_age_h": payee_age_h,
        "device_age_h": device_age_h,
        "device_changed_24h": device_changed,
        "n_pay_1h": n_1h,
        "n_pay_24h": n_24h,
        "sum_1h": s_1h,
        "sum_24h": s_24h,
        "sum_newpayee_1h": s_new_1h,
        "fan_out_1h": len(payees_1h),
        "r_fan_in_24h": fan_in,
        "r_passthrough_1h": passthrough,
        "hour_of_day": h,
        "night_flag": 1 if h < NIGHT_END_H else 0,
    }
    return {k: float(values[k]) for k in FEATURES}
