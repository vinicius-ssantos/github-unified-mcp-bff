import respx
import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.fixture(scope="module")
def client():
    from app.main import app
    with TestClient(app) as c:
        yield c


def test_me_unauthenticated(client):
    r = client.get("/auth/me")
    assert r.status_code == 401


def test_login_oauth_not_configured(client):
    # GITHUB_CLIENT_ID is empty in test env
    r = client.get("/auth/login", follow_redirects=False)
    assert r.status_code == 501


def test_logout_clears_cookie(client):
    r = client.post("/auth/logout")
    assert r.status_code == 200
    assert r.json()["ok"] is True
    set_cookie = ", ".join(r.headers.get_list("set-cookie"))
    assert "bff_session=" in set_cookie
    assert "csrf_token=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "SameSite=lax" in set_cookie


def test_me_with_valid_jwt(client):
    from datetime import datetime, timezone, timedelta
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(seconds=3600)
    token = jwt.encode({"sub": "testuser", "name": "Test User", "exp": exp}, settings.jwt_secret, algorithm="HS256")

    client.cookies.set("bff_session", token)
    r = client.get("/auth/me")
    assert r.status_code == 200
    assert r.json()["user"] == "testuser"
    client.cookies.clear()


@respx.mock
def test_callback_redirects_to_frontend_and_sets_default_cookies(monkeypatch):
    from app.auth import callback
    from app.config import Settings

    settings = Settings(
        mcp_url="http://mock-mcp:8000",
        github_client_id="client-id",
        github_client_secret="client-secret",
        frontend_url="http://localhost:5173",
        jwt_secret="test-secret",
    )
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "gh-token"})
    )
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json={"login": "octocat", "name": "Octo Cat"})
    )
    respx.get("https://api.github.com/user/teams").mock(
        return_value=httpx.Response(200, json=[])
    )

    import anyio
    resp = anyio.run(callback, "code-123", settings)

    assert resp.status_code == 302
    assert resp.headers["location"] == "http://localhost:5173"
    set_cookie = ", ".join(resp.headers.getlist("set-cookie"))
    assert "bff_session=" in set_cookie
    assert "csrf_token=" in set_cookie
    assert "HttpOnly" in set_cookie
    assert "SameSite=lax" in set_cookie
    assert "Secure" not in set_cookie


@respx.mock
def test_callback_supports_cross_origin_secure_none_cookies():
    from app.auth import callback
    from app.config import Settings

    settings = Settings(
        mcp_url="http://mock-mcp:8000",
        github_client_id="client-id",
        github_client_secret="client-secret",
        frontend_url="https://frontend.example.com",
        jwt_secret="test-secret",
        cookie_secure=True,
        cookie_samesite="none",
        cookie_domain=".example.com",
    )
    respx.post("https://github.com/login/oauth/access_token").mock(
        return_value=httpx.Response(200, json={"access_token": "gh-token"})
    )
    respx.get("https://api.github.com/user").mock(
        return_value=httpx.Response(200, json={"login": "octocat", "name": "Octo Cat"})
    )
    respx.get("https://api.github.com/user/teams").mock(
        return_value=httpx.Response(200, json=[])
    )

    import anyio
    resp = anyio.run(callback, "code-123", settings)

    set_cookie = ", ".join(resp.headers.getlist("set-cookie"))
    assert resp.headers["location"] == "https://frontend.example.com"
    assert "Secure" in set_cookie
    assert "SameSite=none" in set_cookie
    assert "Domain=.example.com" in set_cookie
    assert "bff_session=" in set_cookie
    assert "csrf_token=" in set_cookie


def test_logout_uses_configured_cookie_attributes():
    from app.auth import logout
    from app.config import Settings

    settings = Settings(
        mcp_url="http://mock-mcp:8000",
        cookie_secure=True,
        cookie_samesite="none",
        cookie_domain=".example.com",
    )

    import anyio
    resp = anyio.run(logout, settings=settings)

    set_cookie = ", ".join(resp.headers.get_list("set-cookie"))
    assert "bff_session=" in set_cookie
    assert "csrf_token=" in set_cookie
    assert "Max-Age=0" in set_cookie
    assert "Secure" in set_cookie
    assert "SameSite=none" in set_cookie
    assert "Domain=.example.com" in set_cookie
