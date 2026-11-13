"""Owner: M3. take(state) -> Snap; restore(snap) -> State. Deep copy, target
< 50ms — the attacker search loop resets thousands of times."""
from __future__ import annotations

from typing import Any

from fa.contracts import State

Snap = Any


def take(state: State) -> Snap:
    raise NotImplementedError


def restore(snap: Snap) -> State:
    raise NotImplementedError
