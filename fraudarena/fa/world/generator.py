"""Owner: M3. generate_world(seed) -> (State, list[Event]).

30d history + 7d validation + 7d holdout, 2% look-alike payees, seeded with
numpy.random.default_rng(seed). Same seed must give identical traffic twice.
"""
from __future__ import annotations

from fa.contracts import Event, State


def generate_world(seed: int) -> tuple[State, list[Event]]:
    raise NotImplementedError
