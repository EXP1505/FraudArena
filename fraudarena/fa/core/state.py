"""Owner: M3. new_state() -> State; apply(state, ev, decision) -> None,
the only function that mutates state (balance, payees, devices, recent_pays).

State shape: ``SimState`` / ``SimAccount`` subclass the frozen contract types
``fa.contracts.State`` / ``AccountState`` and only ADD fields the receiving-side
features and the hold path need:

    SimState.accounts[acct]  -> SimAccount
        balance, avg_30d, payees{id: first_ts}, devices{id: first_ts},
        recent_pays[(ts, amount, payee)]          # contract fields
        outflows[(ts, amount)]                    # allowed payments + cashouts
        pending[(ts, event_id, amount, payee)]    # held payments
    SimState.inflows[recipient] -> [(ts, sender, amount)]

Lists are ts-sorted and NOT pruned by apply(): features find their window with
bisect, so cost depends on the window, and a feature recomputed for an earlier
time sees exactly what it saw then (no leakage). ``compact(state, ts)`` drops
history no window at or after ``ts`` can reach.

Always build state with ``new_state()`` (or snapshot.restore). A plain
contracts.State also works but has no inflows, so receiving-side features stay 0.

Events may be contracts.Event, dicts or any object with the contract fields.
Phase-1 aliases are accepted: id -> event_id, pay -> payment,
payee_add -> add_payee, device_add -> login.
"""
from __future__ import annotations

from bisect import bisect_left, bisect_right, insort
from operator import itemgetter
from typing import Any, Mapping

from pydantic import Field

from fa.contracts import AccountState, Event, State

from .clock import DAY

PAY_WINDOW_S = 30 * DAY      # amount_ratio_30d / avg_30d window
SHORT_WINDOW_S = DAY         # longest window over outflows / inflows
MIN_PAYS_FOR_AVG = 3         # fewer than this -> amount_ratio_30d = 1.0

EVENT_TYPES = ("login", "add_payee", "payment", "cashout")
TYPE_ALIASES = {"pay": "payment", "payee_add": "add_payee", "device_add": "login"}
EVENT_FIELDS = ("event_id", "ts", "type", "account", "device", "payee", "amount", "channel")
DECISIONS = ("allow", "hold", "block")

_TS = itemgetter(0)


# ---------------------------------------------------------------- types

class SimAccount(AccountState):
    outflows: list[tuple[int, int]] = Field(default_factory=list)
    pending: list[tuple[int, str, int, str | None]] = Field(default_factory=list)


class SimState(State):
    accounts: dict[str, SimAccount] = Field(default_factory=dict)  # type: ignore[assignment]
    inflows: dict[str, list[tuple[int, str, int]]] = Field(default_factory=dict)

    def account(self, account_id: str) -> SimAccount:  # type: ignore[override]
        return ensure_account(self, account_id)


# ---------------------------------------------------------------- events

def ev_get(event: Any, key: str, default: Any = None) -> Any:
    if type(event) is dict:          # fast path: skips the slow typing.Mapping isinstance check
        return event.get(key, default)
    if isinstance(event, Mapping):
        return event.get(key, default)
    return getattr(event, key, default)


def as_event(event: Any) -> dict:
    """Normalise an Event / dict / object to a plain dict with the contract fields."""
    if type(event) is dict:
        d = {k: event.get(k) for k in EVENT_FIELDS}
    else:
        d = {k: ev_get(event, k) for k in EVENT_FIELDS}
    if d["event_id"] is None:
        d["event_id"] = ev_get(event, "id")
    t = d["type"]
    t = getattr(t, "value", t)
    d["type"] = TYPE_ALIASES.get(t, t)
    d["ts"] = int(d["ts"] or 0)
    d["amount"] = int(d["amount"] or 0)
    return d


def to_event(event: Any) -> Event:
    """Contract Event from a dict / object (aliases normalised)."""
    return event if isinstance(event, Event) else Event(**as_event(event))


# ---------------------------------------------------------------- construction

def new_state() -> SimState:
    return SimState()


def new_account(balance: int = 0, payees: Mapping[str, int] | None = None,
                devices: Mapping[str, int] | None = None) -> SimAccount:
    return SimAccount.model_construct(
        balance=int(balance), avg_30d=0.0, payees=dict(payees or {}),
        devices=dict(devices or {}), recent_pays=[], outflows=[], pending=[])


def add_account(state: State, account_id: str, **kwargs) -> SimAccount:
    acc = new_account(**kwargs)
    state.accounts[account_id] = acc
    return acc


def ensure_account(state: State, account_id: str) -> SimAccount:
    acc = state.accounts.get(account_id)
    if acc is None:
        acc = add_account(state, account_id)
    elif not isinstance(acc, SimAccount):           # plain contract AccountState: upgrade
        acc = SimAccount.model_construct(**acc.__dict__, outflows=[], pending=[])
        state.accounts[account_id] = acc
    return acc


# ---------------------------------------------------------------- windows

def window(lst: list, lo_excl: int, hi_excl: int) -> list:
    """Entries of a ts-sorted list with lo_excl < ts < hi_excl."""
    return lst[bisect_right(lst, lo_excl, key=_TS):bisect_left(lst, hi_excl, key=_TS)]


def _append_sorted(lst: list, item: tuple) -> None:
    if not lst or lst[-1][0] <= item[0]:
        lst.append(item)
    else:
        insort(lst, item, key=_TS)


def _prune(lst: list, cutoff: int) -> None:
    i = bisect_right(lst, cutoff, key=_TS)
    if i:
        del lst[:i]


def compact(state: State, now: int) -> State:
    """Drop history no feature window at time >= now can reach. In place."""
    for acc in state.accounts.values():
        _prune(acc.recent_pays, now - PAY_WINDOW_S)
        _prune(getattr(acc, "outflows", []), now - SHORT_WINDOW_S)
    for lst in getattr(state, "inflows", {}).values():
        _prune(lst, now - SHORT_WINDOW_S)
    return state


# ---------------------------------------------------------------- apply

def apply(state: State, ev: Any, decision: str = "allow") -> None:
    """Apply one event with the engine's decision. The ONLY state mutator.

    allow  money moves; payment enters history; recipient inflow recorded
    hold   payment goes to the account's pending list; no money moves
    block  rejected; no money moves
    In every case the device and payee are recorded as seen.
    """
    decision = getattr(decision, "decision", decision)     # accept a Decision too
    if decision not in DECISIONS:
        raise ValueError(f"unknown decision: {decision!r}")
    e = as_event(ev)
    etype = e["type"]
    if etype not in EVENT_TYPES:
        raise ValueError(f"unknown event type: {etype!r}")
    ts = e["ts"]
    acc = ensure_account(state, e["account"])

    device = e["device"]
    if device and device not in acc.devices:
        acc.devices[device] = ts

    payee = e["payee"]
    if etype in ("add_payee", "payment") and payee and payee not in acc.payees:
        acc.payees[payee] = ts

    if etype not in ("payment", "cashout"):
        return
    amount = e["amount"]
    if decision == "hold":
        if etype == "payment":
            acc.pending.append((ts, e["event_id"], amount, payee))
        return
    if decision == "block":
        return

    acc.balance -= amount
    _append_sorted(acc.outflows, (ts, amount))
    if etype == "payment":
        _append_sorted(acc.recent_pays, (ts, amount, payee))
        if payee:
            inflows = getattr(state, "inflows", None)
            if inflows is not None:
                _append_sorted(inflows.setdefault(payee, []), (ts, e["account"], amount))
            dest = state.accounts.get(payee)
            if dest is not None:
                dest.balance += amount
        pays = window(acc.recent_pays, ts - PAY_WINDOW_S, ts + 1)
        acc.avg_30d = sum(p[1] for p in pays) / len(pays)
