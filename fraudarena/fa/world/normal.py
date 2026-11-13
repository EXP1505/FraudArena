"""Owner: M3. Seeded normal-traffic generation helpers (customers, segments,
devices, payees, log-normal amounts, daytime curve, recurring rent/bills).
Used by fa.world.generator.generate_world.
"""
from __future__ import annotations

import numpy as np


def generate_normal_events(rng: np.random.Generator, accounts: int, days: int) -> list[dict]:
    raise NotImplementedError
