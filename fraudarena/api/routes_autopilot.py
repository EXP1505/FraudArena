"""Owner: M4. GET /api/playbooks, POST /api/autopilot/start|stop, GET /api/autopilot."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from api import auth, autopilot
from fa.plans import invent

router = APIRouter(prefix="/api")
ALLOWED = ("P1", "P2", "P3", "NEW")


class AutopilotRequest(BaseModel):
    rounds: int = Field(default=6, ge=1, le=30)
    interval_s: int = Field(default=5, ge=0, le=3600)
    playbooks: list[str] = Field(default_factory=lambda: ["P1", "P2", "P3", "NEW"], min_length=1)
    max_pending: int = Field(default=3, ge=1, le=10)


@router.get("/playbooks")
def playbooks() -> list[dict]:
    """The three built-in attack types plus every attack the AI has invented so far, with its approach."""
    out = [{"id": k, "name": v[0], "idea": v[1], "why": v[2], "origin": "built-in"} for k, v in invent.BUILTIN.items()]
    for s in invent.all_specs():
        out.append({"id": s["id"], "name": s["name"], "idea": s["approach"], "why": s["why_it_might_work"],
                    "origin": "invented by the attacker AI" if s["source"] == "llm" else "built-in idea (no AI key)",
                    "steps": s["steps"]})
    return out


@router.get("/autopilot")
def get_autopilot() -> dict:
    return autopilot.status()


@router.post("/autopilot/start")
def start_autopilot(req: AutopilotRequest, request: Request) -> dict:
    bad = [p for p in req.playbooks if p not in ALLOWED]
    if bad:
        raise HTTPException(status_code=422, detail=f"unknown playbook(s) {bad}; use {list(ALLOWED)}")
    return autopilot.start(req.rounds, req.interval_s, req.playbooks, req.max_pending, auth.current_email(request))


@router.post("/autopilot/stop")
def stop_autopilot() -> dict:
    return autopilot.stop()
