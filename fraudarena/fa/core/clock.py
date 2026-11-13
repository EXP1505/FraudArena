# Owner: M3. Simulated clock (integer seconds, never time.time()).
"""Simulated time.

Sim time is an integer number of seconds since the simulation epoch (day 0, 00:00),
so ``hour_of_day(ts)`` needs no calendar. Time only moves when a caller advances it;
nothing under fa/ reads the wall clock.
"""

MINUTE = 60
HOUR = 3600
DAY = 86400


def hour_of_day(ts: int) -> int:
    return (int(ts) // HOUR) % 24


def day_of(ts: int) -> int:
    return int(ts) // DAY


class Clock:
    """Monotonic integer clock: ``Clock(start).now()``, ``.advance(s)``, ``.set(ts)``."""

    __slots__ = ("_now",)

    def __init__(self, start: int = 0):
        self._now = int(start)

    def now(self) -> int:
        return self._now

    def advance(self, s: int) -> int:
        s = int(s)
        if s < 0:
            raise ValueError("clock cannot move backwards")
        self._now += s
        return self._now

    def set(self, ts: int) -> int:
        ts = int(ts)
        if ts < self._now:
            raise ValueError(f"clock cannot move backwards ({ts} < {self._now})")
        self._now = ts
        return self._now

    def __repr__(self) -> str:
        return f"Clock(now={self._now}, day={day_of(self._now)}, hour={hour_of_day(self._now)})"
