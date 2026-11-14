"""Owner: M4. GET /api/credits, POST /api/credits/grant, GET /api/digest, POST /api/digest/seen."""
from __future__ import annotations

import calendar
import os
import time

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api import auth, credits
from api.db import list_rounds
from fa.release.versions import ACTIVE, AWAITING_APPROVAL, default_store

router = APIRouter(prefix="/api")
HOLE_STATES = {"AWAITING_APPROVAL", "NO_SAFE_PATCH", "REJECTED_BY_GATES", "APPROVED", "REJECTED"}


class Grant(BaseModel):
    amount: int = Field(ge=1, le=10_000)
    email: str | None = None


@router.get("/credits")
def get_credits(request: Request) -> dict:
    user = auth.current_email(request)
    a = credits.account(user)
    return {"user": user, "balance": a["balance"], "spent": a["spent"], "starting": credits.START,
            "costs": credits.COSTS, "history": a["history"][:12]}


@router.post("/credits/grant")
def grant(body: Grant, request: Request) -> dict:
    """Top up a user. With sign-in off anyone may (it is a local demo); with it on, only AUTH_ADMIN_EMAILS."""
    me = auth.current_email(request)
    admins = {x.strip().lower() for x in (os.environ.get("AUTH_ADMIN_EMAILS") or "").split(",") if x.strip()}
    if auth.enabled() and me.lower() not in admins:
        raise HTTPException(status_code=403, detail="Only an admin can add credits.")
    target = body.email or me
    return {"user": target, "balance": credits.grant(target, body.amount, f"Top-up by {me}")}


def _ts(s: str) -> float:
    try:
        return calendar.timegm(time.strptime(str(s)[:19], "%Y-%m-%d %H:%M:%S"))
    except ValueError:
        return 0.0


@router.get("/digest")
def digest(request: Request) -> dict:
    """"Since you were last here": what the attacker did and what needs a person. Drives the welcome card."""
    user = auth.current_email(request)
    a = credits.account(user)
    since = a["last_seen"]
    rounds = [r for r in list_rounds() if since is None or _ts(r["created_at"]) > since]
    patches = default_store().list_patches()
    waiting = [p for p in patches if p.get("state") == AWAITING_APPROVAL]
    approved = [p for p in patches if p.get("state") == ACTIVE and (since is None or (p.get("created_at") or 0) > since)]
    from fa.verify import regression
    out = {
        "user": user, "first_visit": since is None, "since": since, "balance": a["balance"],
        "rounds": len(rounds), "ai_attacks": sum(1 for r in rounds if str(r["playbook"]).startswith("X-")),
        "holes_found": sum(1 for r in rounds if r["state"] in HOLE_STATES),
        "fixes_waiting": len(waiting), "fixes_approved": len(approved),
        "guarded_attacks": len(regression.all()),
    }
    out["worth_showing"] = out["first_visit"] or out["rounds"] > 0 or out["fixes_waiting"] > 0
    return out


@router.post("/digest/seen")
def seen(request: Request) -> dict:
    credits.mark_seen(auth.current_email(request))
    return {"ok": True}
