"""Owner: M3. Simulated clock: integer seconds, never time.time()."""
from __future__ import annotations


class Clock:
    def __init__(self, start: int = 0) -> None:
        raise NotImplementedError

    def now(self) -> int:
        raise NotImplementedError

    def advance(self, s: int) -> None:
        raise NotImplementedError
