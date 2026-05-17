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
