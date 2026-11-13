"""Owner: M3. compute_features(state, ev) -> dict[str, float]: the 12
agreed features (fa.contracts.FEATURES), computed from state BEFORE ev is
applied. Never read anything from after ev.ts (no leakage, test 3)."""
from __future__ import annotations

from fa.contracts import Event, State


def compute_features(state: State, ev: Event) -> dict[str, float]:
    raise NotImplementedError
