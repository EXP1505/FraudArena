"""Owner: M4. GET /api/auth/config, GET /api/auth/me, POST /api/auth/google, POST /api/auth/logout."""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel

from api import auth

router = APIRouter(prefix="/api/auth")


class GoogleLogin(BaseModel):
    credential: str


@router.get("/config")
def config() -> dict:
    return {"enabled": auth.enabled(), "client_id": auth.client_id() or None, "restricted": auth.restricted()}


@router.get("/me")
def me(request: Request) -> dict:
    user = auth.read_session(request.cookies.get(auth.COOKIE))
    return {"enabled": auth.enabled(), "user": user and {k: user.get(k) for k in ("email", "name", "picture")}}


@router.post("/google")
def google_login(body: GoogleLogin, request: Request, response: Response) -> dict:
    if not auth.enabled():
        raise HTTPException(status_code=400, detail="Google sign-in is not configured (set GOOGLE_CLIENT_ID).")
    try:
        user = auth.verify_google(body.credential)
    except ValueError as exc:
        raise HTTPException(status_code=401, detail=str(exc)) from exc
    if not auth.allowed(user["email"]):
        raise HTTPException(status_code=403, detail=f"{user['email']} is not on the list of people allowed in.")
    response.set_cookie(auth.COOKIE, auth.make_session(user), max_age=auth.SESSION_SECONDS, httponly=True,
                        samesite="lax", secure=request.url.scheme == "https", path="/")
    return {"enabled": True, "user": user}


@router.post("/logout")
def logout(response: Response) -> dict:
    response.delete_cookie(auth.COOKIE, path="/")
    return {"ok": True}
