"""Owner: M2. psycopg connection pool and batch insert helpers (batches of
1,000 rows when the simulator runs in bulk; single-row writes for POST /tx).
"""
from __future__ import annotations


def get_pool():
    raise NotImplementedError


def insert_event(conn, event: dict) -> None:
    raise NotImplementedError


def insert_events_batch(conn, events: list[dict]) -> None:
    raise NotImplementedError
