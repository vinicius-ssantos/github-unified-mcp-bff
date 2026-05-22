from datetime import datetime, timedelta, timezone

import pytest
from fastapi.testclient import TestClient
from jose import jwt


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def _session_token(settings, sub="testuser", name="Test User", teams=None):
    exp = datetime.now(timezone.utc) + timedelta(seconds=3600)
    return jwt.encode(
        {
            "sub": sub,
            "name": name,
            "teams": teams or [],
            "csrf": "csrf-token",
            "exp": exp,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def test_capabilities_anonymous_payload_is_safe(client):
    r = client.get("/api/capabilities")

    assert r.status_code == 200
    data = r.json()
    assert data["service"] == "github-unified-mcp-bff"
    assert data["authenticated"] is False
    assert data["user"] is None
    assert data["auth"]["cookie_session"] is True
    assert data["auth"]["csrf_required"] is False
    assert data["mcp"]["raw_passthrough_enabled"] is True
    assert data["mcp"]["raw_tool_execution_enabled"] is True
    assert data["mcp"]["structured_call_enabled"] is True
    assert data["features"]["audit_protected"] is True
    assert data["features"]["controlled_operations"] is True
    assert data["features"]["operation_preview"] is True
    assert data["features"]["operation_confirmation"] is True
    assert data["features"]["operation_execution"] is False
    assert data["features"]["tool_policy"] is True
    assert data["features"]["unknown_tools_blocked"] is True


def test_capabilities_authenticated_user_payload(client):
    from app.config import get_settings

    settings = get_settings()
    client.cookies.set("bff_session", _session_token(settings))
    r = client.get("/api/capabilities")

    assert r.status_code == 200
    data = r.json()
    assert data["authenticated"] is True
    assert data["user"] == {"login": "testuser", "name": "Test User", "role": "viewer"}
    assert data["auth"]["csrf_required"] is True
    client.cookies.clear()


def test_capabilities_reflects_admin_role(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_admin_users", "adminuser")
    client.cookies.set("bff_session", _session_token(settings, sub="adminuser", name="Admin User"))
    r = client.get("/api/capabilities")

    assert r.status_code == 200
    assert r.json()["user"]["role"] == "admin"
    client.cookies.clear()


def test_capabilities_exposes_static_bearer_auth_mode(client):
    r = client.get("/api/capabilities")
    assert r.status_code == 200
    assert r.json()["mcp"]["auth_mode"] == "static_bearer"
