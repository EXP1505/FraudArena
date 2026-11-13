"""Owner: M4. Wilson score interval (24h plan section 8).

p = k/n, z = 1.96:
  centre     = (p + z^2/2n) / (1 + z^2/n)
  half-width = z * sqrt(p(1-p)/n + z^2/4n^2) / (1 + z^2/n)
"""
from __future__ import annotations

import math

Z95 = 1.96


def wilson_interval(k: int, n: int, z: float = Z95) -> tuple[float, float]:
    """95% Wilson interval (lo, hi) for k successes in n trials. n == 0 -> (0, 1)."""
    if n < 0 or k < 0 or k > n:
        raise ValueError(f"need 0 <= k <= n, got k={k}, n={n}")
    if n == 0:
        return 0.0, 1.0
    p = k / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


def wilson_upper(k: int, n: int, z: float = Z95) -> float:
    return wilson_interval(k, n, z)[1]
