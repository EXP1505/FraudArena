"""Owner: M2. FastAPI app. Pre-wired per docs/TIMELINE.md golden rule: routers
for routes_core, routes_rounds, routes_ledger, routes_release are included
here once and for all — nobody needs to touch this file again to add routes.
"""
from __future__ import annotations

from contextlib import asynccontextmanager

from fastapi import FastAPI

from api import routes_core, routes_ledger, routes_release, routes_rounds


def load_active_ruleset() -> None:
    """Load fa/rules/baseline_v1.json into rule_versions if the table is empty."""
    raise NotImplementedError


@asynccontextmanager
async def lifespan(app: FastAPI):
    load_active_ruleset()
    yield


app = FastAPI(title="FraudArena API", lifespan=lifespan)

app.include_router(routes_core.router)
app.include_router(routes_rounds.router)
app.include_router(routes_ledger.router)
app.include_router(routes_release.router)
