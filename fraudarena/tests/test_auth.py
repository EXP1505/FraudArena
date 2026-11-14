"""Owner: M4. Google sign-in: off by default; when on, the API needs a valid signed session."""
from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from api import auth
from api.main import app

USER = {"email": "alice@bank.com", "name": "Alice", "picture": None}


@pytest.fixture
def client(monkeypatch, tmp_path):
    from api.db import init_db
    init_db()
    monkeypatch.setenv("FA_AUTH_SECRET_PATH", str(tmp_path / "secret"))
    for k in ("GOOGLE_CLIENT_ID", "AUTH_ALLOWED_EMAILS", "AUTH_ALLOWED_DOMAINS", "AUTH_SECRET"):
        monkeypatch.delenv(k, raising=False)
    return TestClient(app)


def _on(monkeypatch, verifier=lambda c: USER):
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc.apps.googleusercontent.com")
    monkeypatch.setattr(auth, "verify_google", verifier)


def test_off_by_default_nothing_is_protected(client):
    assert client.get("/api/auth/config").json() == {"enabled": False, "client_id": None, "restricted": False}
    assert client.get("/api/rounds").status_code == 200
    assert client.post("/api/auth/google", json={"credential": "x"}).status_code == 400


def test_when_on_the_api_needs_a_session(client, monkeypatch):
    _on(monkeypatch)
    assert client.get("/api/rounds").status_code == 401
    assert client.get("/api/auth/config").json()["client_id"].startswith("abc")      # public, needed to draw the button
    assert client.get("/health").status_code == 200                                    # liveness stays open
    assert client.get("/api/auth/me").json() == {"enabled": True, "user": None}
    r = client.post("/api/auth/google", json={"credential": "token"})
    assert r.status_code == 200 and r.json()["user"]["email"] == "alice@bank.com"
    assert "httponly" in r.headers["set-cookie"].lower() and "samesite=lax" in r.headers["set-cookie"].lower()
    assert client.get("/api/rounds").status_code == 200
    assert client.get("/api/auth/me").json()["user"]["name"] == "Alice"
    client.post("/api/auth/logout")
    assert client.get("/api/rounds").status_code == 401


def test_allow_list_by_email_and_domain(client, monkeypatch):
    _on(monkeypatch)
    monkeypatch.setenv("AUTH_ALLOWED_DOMAINS", "other.com")
    assert client.post("/api/auth/google", json={"credential": "t"}).status_code == 403
    monkeypatch.setenv("AUTH_ALLOWED_DOMAINS", "BANK.com")
    assert client.post("/api/auth/google", json={"credential": "t"}).status_code == 200
    client.post("/api/auth/logout")
    monkeypatch.setenv("AUTH_ALLOWED_DOMAINS", "")
    monkeypatch.setenv("AUTH_ALLOWED_EMAILS", "bob@bank.com")
    assert client.post("/api/auth/google", json={"credential": "t"}).status_code == 403


def test_a_bad_google_token_is_refused_with_a_message(client, monkeypatch):
    def bad(_):
        raise ValueError("Google could not confirm this sign-in (Exception).")
    _on(monkeypatch, bad)
    r = client.post("/api/auth/google", json={"credential": "forged"})
    assert r.status_code == 401 and "could not confirm" in r.json()["detail"]
    assert client.get("/api/rounds").status_code == 401


def test_session_cookie_cannot_be_forged_or_reused_after_expiry(client, monkeypatch):
    tok = auth.make_session(USER)
    assert auth.read_session(tok)["email"] == "alice@bank.com"
    body, sig = tok.rsplit(".", 1)
    assert auth.read_session(body + "." + sig[:-2] + "AA") is None                      # tampered signature
    forged = auth._b64(b'{"email":"evil@x.com","exp":99999999999}') + "." + sig
    assert auth.read_session(forged) is None                                           # swapped payload
    assert auth.read_session(tok, now=10**11) is None                                  # expired
    assert auth.read_session("garbage") is None and auth.read_session(None) is None
    monkeypatch.setenv("AUTH_SECRET", "another-secret")
    assert auth.read_session(tok) is None                                              # signed with a different key


def test_unverified_google_email_is_refused(monkeypatch):
    class Fake:
        pass
    import google.oauth2.id_token as idt
    monkeypatch.setenv("GOOGLE_CLIENT_ID", "abc")
    monkeypatch.setattr(idt, "verify_oauth2_token", lambda *a, **k: {"iss": "accounts.google.com", "email": "a@b.com", "email_verified": False})
    with pytest.raises(ValueError, match="not verified"):
        auth.verify_google("t")
    monkeypatch.setattr(idt, "verify_oauth2_token", lambda *a, **k: {"iss": "evil.com", "email": "a@b.com", "email_verified": True})
    with pytest.raises(ValueError, match="not issued by Google"):
        auth.verify_google("t")
    monkeypatch.setattr(idt, "verify_oauth2_token", lambda *a, **k: (_ for _ in ()).throw(Exception("bad aud")))
    with pytest.raises(ValueError, match="could not confirm"):
        auth.verify_google("t")
