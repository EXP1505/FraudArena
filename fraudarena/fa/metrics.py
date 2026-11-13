"""Owner: M3. hold_rate(decisions) -> (p, lo, hi) using fa.verify.wilson;
wcel(traces) -> int (worst-case expected loss); plus the experiment runner
that writes the `metrics` table: WCEL per playbook per version, hold rate
with a Wilson interval, detection delay, random-search baseline."""
from __future__ import annotations

from fa.contracts import Decision, Trace


def hold_rate(decisions: list[Decision]) -> tuple[float, float, float]:
    raise NotImplementedError


def wcel(traces: list[Trace]) -> int:
    raise NotImplementedError
