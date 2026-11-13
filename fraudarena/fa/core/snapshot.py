"""Owner: M3. take(state) -> Snap; restore(snap) -> State. Target < 50 ms: the
attacker search loop resets thousands of times.

Cheaper than copy.deepcopy / model_copy(deep=True): history tuples are immutable
and shared; dicts and lists are copied; models are rebuilt with model_construct
(no re-validation). A snapshot is never mutated by restore(); restore it any
number of times.
"""
from __future__ import annotations

from typing import Any

from fa.contracts import State
from fa.core.state import SimAccount, SimState

Snap = Any


def _copy_account(a) -> SimAccount:
    return SimAccount.model_construct(
        balance=a.balance,
        avg_30d=a.avg_30d,
        payees=dict(a.payees),
        devices=dict(a.devices),
        recent_pays=list(a.recent_pays),
        outflows=list(getattr(a, "outflows", ())),
        pending=list(getattr(a, "pending", ())),
    )


def _copy(state: State) -> SimState:
    return SimState.model_construct(
        accounts={k: _copy_account(v) for k, v in state.accounts.items()},
        inflows={k: list(v) for k, v in getattr(state, "inflows", {}).items()},
    )


def take(state: State) -> Snap:
    """Independent copy of ``state``."""
    return _copy(state)


def restore(snap: Snap) -> State:
    """Fresh working state from ``snap``; the snapshot stays reusable."""
    return _copy(snap)
