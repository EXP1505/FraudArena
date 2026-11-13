"""Owner: M1. make demo: reset world -> run round -> approve patch -> show chart.

Coded against M2's /api/world/reset and /api/metrics, and fa.orchestrator.run_round
-- the round/approval endpoints are still owned stubs until M2/M4 land them.
"""
from __future__ import annotations

import os

import httpx

from fa.orchestrator import run_round

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
DEFAULT_PLAYBOOK = "P1"


def main() -> None:
    with httpx.Client(base_url=API_BASE_URL, timeout=30) as client:
        resp = client.post("/api/world/reset")
        resp.raise_for_status()
        print("world reset:", resp.json())

    round_id = run_round(DEFAULT_PLAYBOOK, started_by="demo-script")
    print(f"round {round_id} started for playbook {DEFAULT_PLAYBOOK}")
    print("approve the proposed patch in the dashboard's Patch view, then re-run "
          "this script to see the next round, or check GET /api/metrics for the chart.")


if __name__ == "__main__":
    main()
