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
from fastapi.responses import JSONResponse

from api import auth, routes_auth, routes_credits, routes_autopilot, routes_core, routes_export, routes_fidelity, routes_ledger, routes_release, routes_rounds
from api.db import init_db, get_rules_for_version, save_rule_version

# One rules file for everyone: M4's generated baseline (R2 ratio 6), not a second copy.
RULES_PATH = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "fa", "rules", "baseline_v1.json")

def load_active_ruleset() -> None:
    """Load rule set v1 (policy pack if a real RBIH bundle is installed, else the hand baseline)
    into rule_versions if the table is empty, and drop stale v1 measurements when v1 changed."""
    import hashlib

    from fa.rules.loader import baseline_source, load_baseline

    rules = [r.model_dump(mode="json") for r in load_baseline().rules]
    sig = baseline_source() + ":" + hashlib.sha256(json.dumps(rules, sort_keys=True).encode()).hexdigest()[:16]
    sig_path = os.path.join(os.path.dirname(RULES_PATH), "..", "..", "data", "baseline.sig")
    try:
        old = open(sig_path, encoding="utf-8").read().strip() if os.path.exists(sig_path) else None
        if old != sig:
            from api.db import clear_v1_metrics
            clear_v1_metrics()
            os.makedirs(os.path.dirname(sig_path), exist_ok=True)
            open(sig_path, "w", encoding="utf-8").write(sig)
    except Exception:
        pass
    if not get_rules_for_version(1):
        save_rule_version(1, rules, source="baseline")


@asynccontextmanager
async def lifespan(app: FastAPI):
    init_db()
    load_active_ruleset()
    yield

app = FastAPI(title="FraudArena API", lifespan=lifespan)

# With sign-in on, a wildcard CORS policy plus cookies would let any website read signed-in responses: only the
# listed origins (default: the local dev site) may call the API with the session cookie.
_origins = [o.strip() for o in os.environ.get("AUTH_ORIGINS", "http://localhost:5173").split(",") if o.strip()]
app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins if auth.enabled() else ["*"],
    allow_credentials=auth.enabled(),
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.middleware("http")
async def require_sign_in(request, call_next):
    """When Google sign-in is configured, every /api route except /api/auth/* needs a valid session cookie."""
    p = request.url.path
    if auth.enabled() and p.startswith("/api/") and not p.startswith("/api/auth/") and request.method != "OPTIONS":
        if auth.read_session(request.cookies.get(auth.COOKIE)) is None:
            return JSONResponse({"detail": "Please sign in."}, status_code=401)
    return await call_next(request)


app.include_router(routes_core.router)
app.include_router(routes_rounds.router)
app.include_router(routes_ledger.router)
app.include_router(routes_release.router)
app.include_router(routes_export.router)
app.include_router(routes_fidelity.router)
app.include_router(routes_autopilot.router)
app.include_router(routes_auth.router)
app.include_router(routes_credits.router)
