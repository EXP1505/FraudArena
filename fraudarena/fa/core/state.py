"""Owner: M3. new_state() -> State; apply(state, ev, decision) -> None,
the only function that mutates state (balance, payees, devices, recent_pays).
"""
from __future__ import annotations

from fa.contracts import Event, State


def new_state() -> State:
    raise NotImplementedError


def apply(state: State, ev: Event, decision: str) -> None:
    raise NotImplementedError
