"""Owner: M3. golden_cases() -> list[list[Event]]: ~200 benign-but-unusual
cases (rent to new landlord, pay after phone change, festival 5-10x, new
supplier). Used by M4's gate G6 — every case must stay allowed by v1."""
from __future__ import annotations

from fa.contracts import Event


def golden_cases() -> list[list[Event]]:
    raise NotImplementedError
