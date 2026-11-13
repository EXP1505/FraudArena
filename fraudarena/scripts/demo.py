"""Owner: M1. make demo: reset world -> run round -> approve patch -> show chart.

fa.orchestrator.run_round is real end to end through SEARCH/EVALUATE and
raises NotImplementedError once it reaches DEFEND (M3's fa.ml.mine_rules
and fa.world.golden are still stubs). The /api/world/reset and /api/metrics
calls are best-effort: M2's routes_rounds.py doesn't implement them for
real yet, so a connection error or 501 there is reported, not fatal --
the round itself doesn't go through the API at all.
"""
from __future__ import annotations

import os
import sys

PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if PROJECT_ROOT not in sys.path:
    sys.path.insert(0, PROJECT_ROOT)

import httpx

from fa.orchestrator import run_round

API_BASE_URL = os.environ.get("API_BASE_URL", "http://localhost:8000")
DEFAULT_PLAYBOOK = "P1"


def _best_effort_reset() -> None:
    try:
        with httpx.Client(base_url=API_BASE_URL, timeout=5) as client:
            resp = client.post("/api/world/reset")
            resp.raise_for_status()
            print("world reset via API:", resp.json())
    except (httpx.HTTPError, NotImplementedError) as exc:
        print(f"world reset skipped ({exc}); continuing without it -- run_round does not need the API")


def main() -> None:
    _best_effort_reset()

    round_id = run_round(DEFAULT_PLAYBOOK, started_by="demo-script")
    print(f"round {round_id} finished for playbook {DEFAULT_PLAYBOOK}")
    print("approve the proposed patch in the dashboard's Patch view, then re-run "
          "this script to see the next round, or check GET /api/metrics for the chart.")


if __name__ == "__main__":
    main()
