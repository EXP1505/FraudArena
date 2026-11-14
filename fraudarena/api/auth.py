"""Owner: M4. Google sign-in (Google Identity Services) with a signed session cookie.

Flow: the browser shows Google's button, Google returns a signed ID token (a JWT) to the page, the page posts it to
POST /api/auth/google, we verify it against Google's public keys (audience = our client id, email verified), check the
allow-list, and set an HttpOnly session cookie. No client secret is needed, and no password is ever seen by us.

Off by default: auth is enforced only when GOOGLE_CLIENT_ID is set, so the demo and the tests run unchanged.
Who may sign in (all optional, comma separated; with none set, any Google account may):
  AUTH_ALLOWED_EMAILS=alice@bank.com,bob@bank.com     AUTH_ALLOWED_DOMAINS=bank.com
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import secrets
import time
from pathlib import Path

COOKIE = "fa_session"
SESSION_SECONDS = 12 * 3600


def client_id() -> str:
    return (os.environ.get("GOOGLE_CLIENT_ID") or "").strip()


def enabled() -> bool:
    return bool(client_id())


def _csv(name: str) -> set[str]:
    return {x.strip().lower() for x in (os.environ.get(name) or "").split(",") if x.strip()}


def restricted() -> bool:
    return bool(_csv("AUTH_ALLOWED_EMAILS") or _csv("AUTH_ALLOWED_DOMAINS"))


def allowed(email: str) -> bool:
    emails, domains = _csv("AUTH_ALLOWED_EMAILS"), _csv("AUTH_ALLOWED_DOMAINS")
    if not emails and not domains:
        return True
    e = email.lower()
    return e in emails or e.rsplit("@", 1)[-1] in domains


def _secret() -> bytes:
    env = os.environ.get("AUTH_SECRET")
    if env:
        return env.encode()
    p = Path(os.environ.get("FA_AUTH_SECRET_PATH", "data/.auth_secret"))
    try:
        return p.read_bytes()
    except OSError:
        s = secrets.token_bytes(32)
        try:
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(s)
            p.chmod(0o600)
        except OSError:
            pass
        return s


def _b64(b: bytes) -> str:
    return base64.urlsafe_b64encode(b).decode().rstrip("=")


def make_session(user: dict, now: float | None = None) -> str:
    body = _b64(json.dumps({**user, "exp": int((now or time.time()) + SESSION_SECONDS)}, separators=(",", ":")).encode())
    return f"{body}.{_b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())}"


def read_session(token: str | None, now: float | None = None) -> dict | None:
    if not token or "." not in token:
        return None
    body, sig = token.rsplit(".", 1)
    good = _b64(hmac.new(_secret(), body.encode(), hashlib.sha256).digest())
    if not hmac.compare_digest(sig, good):
        return None
    try:
        data = json.loads(base64.urlsafe_b64decode(body + "=" * (-len(body) % 4)))
    except ValueError:
        return None
    if data.get("exp", 0) < (now or time.time()):
        return None
    return data


def verify_google(credential: str) -> dict:
    """Check a Google ID token. Returns {email, name, picture}; raises ValueError with a safe message."""
    from google.auth.transport import requests as greq
    from google.oauth2 import id_token

    try:
        info = id_token.verify_oauth2_token(credential, greq.Request(), client_id())
    except Exception as exc:  # noqa: BLE001 - bad signature, wrong audience, expired, offline...
        raise ValueError(f"Google could not confirm this sign-in ({type(exc).__name__}).") from exc
    if info.get("iss") not in ("accounts.google.com", "https://accounts.google.com"):
        raise ValueError("Sign-in was not issued by Google.")
    if not info.get("email_verified"):
        raise ValueError("Your Google email address is not verified.")
    return {"email": info["email"], "name": info.get("name") or info["email"], "picture": info.get("picture")}


def current_email(request) -> str:
    """Who is acting. With sign-in off there is one local demo user."""
    if not enabled():
        return "demo@local"
    u = read_session(request.cookies.get(COOKIE))
    return u["email"] if u else "demo@local"
