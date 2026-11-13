"""Owner: M2. FastAPI app. Pre-wired per docs/TIMELINE.md golden rule: routers
for routes_core, routes_rounds, routes_ledger, routes_release are included
here once and for all — nobody needs to touch this file again to add routes.
"""
from __future__ import annotations

import os
import json
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from api import routes_core, routes_ledger, routes_release, routes_rounds
from api.db import init_db, get_rules_for_version, save_rule_version

# One rules file for everyone: M4's generated baseline (R2 ratio 6), not a second copy.
RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fa", "rules", "baseline_v1.json")

def load_active_ruleset() -> None:
    """Load baseline_v1.json into rule_versions if the table is empty."""
    if not get_rules_for_version(1):
        rules = []
        if os.path.exists(RULES_PATH):
            with open(RULES_PATH, "r", encoding="utf-8") as f:
                rules = json.load(f)
        else:
            rules = [
                {"id": "R3", "action": "block", "when": [{"f": "n_pay_1h", "op": ">=", "v": 12.0}]},
                {"id": "R5", "action": "block", "when": [{"f": "fan_out_1h", "op": ">=", "v": 8.0}]},
                {"id": "R2", "action": "hold", "when": [{"f": "payee_age_h", "op": "<", "v": 1.0}, {"f": "amount_ratio_30d", "op": ">=", "v": 6.0}]},
                {"id": "R1", "action": "hold", "when": [{"f": "amount_ratio_30d", "op": ">=", "v": 10.0}]},
                {"id": "R4", "action": "hold", "when": [{"f": "device_changed_24h", "op": "==", "v": 1}, {"f": "sum_1h", "op": ">=", "v": 50000.0}]},
                {"id": "R6", "action": "hold", "when": [{"f": "night_flag", "op": "==", "v": 1}, {"f": "amount_ratio_30d", "op": ">=", "v": 6.0}]}
            ]
        save_rule_version(1, rules, source="baseline")

@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    load_active_ruleset()
    yield

app = FastAPI(title="FraudArena API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(routes_core.router)
app.include_router(routes_rounds.router)
app.include_router(routes_ledger.router)
app.include_router(routes_release.router)
