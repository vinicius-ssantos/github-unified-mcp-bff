from datetime import datetime, timedelta, timezone

import aiosqlite
import pytest
from fastapi.testclient import TestClient
from jose import jwt

from app.audit import SCHEMA_VERSION, init_db


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


def _set_session(client, settings, sub="testuser", teams=None):
    client.cookies.set("bff_session", _session_token(settings, sub=sub, teams=teams))


def test_audit_requires_authentication(client):
    client.cookies.clear()
    r = client.get("/api/audit")
    assert r.status_code == 401


def test_audit_health_requires_authentication(client):
    client.cookies.clear()
    r = client.get("/api/audit/health")
    assert r.status_code == 401


def test_audit_rejects_viewer(client):
    from app.config import get_settings

    settings = get_settings()
    client.cookies.clear()
    _set_session(client, settings, sub="viewer-user")

    r = client.get("/api/audit")

    assert r.status_code == 403
    assert "operator or admin" in r.json()["detail"]
    client.cookies.clear()


def test_audit_allows_operator(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-audit-user")
    client.cookies.clear()
    _set_session(client, settings, sub="operator-audit-user")

    r = client.get("/api/audit")

    assert r.status_code == 200
    data = r.json()
    assert "events" in data
    assert "total" in data
    client.cookies.clear()


def test_audit_allows_admin(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_admin_users", "admin-audit-user")
    client.cookies.clear()
    _set_session(client, settings, sub="admin-audit-user")

    r = client.get("/api/audit")

    assert r.status_code == 200
    client.cookies.clear()


def test_audit_health_allows_operator(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-health-user")
    client.cookies.clear()
    _set_session(client, settings, sub="operator-health-user")

    r = client.get("/api/audit/health")

    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["backend"] == "sqlite"
    assert data["schema_version"] == str(SCHEMA_VERSION)
    assert "events_total" in data
    assert "retention_days" in data
    client.cookies.clear()


def test_audit_pagination_params_authorized(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-pagination-user")
    client.cookies.clear()
    _set_session(client, settings, sub="operator-pagination-user")

    r = client.get("/api/audit?limit=10&offset=0")

    assert r.status_code == 200
    client.cookies.clear()


def test_audit_filter_by_tool_authorized(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-tool-user")
    client.cookies.clear()
    _set_session(client, settings, sub="operator-tool-user")

    r = client.get("/api/audit?tool=server_info")

    assert r.status_code == 200
    for event in r.json()["events"]:
        assert "server_info" in event["tool"]
    client.cookies.clear()


def test_audit_filter_by_user_authorized(client, monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-user-filter")
    client.cookies.clear()
    _set_session(client, settings, sub="operator-user-filter")

    r = client.get("/api/audit?user=anonymous")

    assert r.status_code == 200
    client.cookies.clear()


def test_audit_limit_max_still_applies_before_auth(client):
    client.cookies.clear()
    r = client.get("/api/audit?limit=201")
    assert r.status_code == 422


@pytest.mark.asyncio
async def test_init_db_writes_schema_metadata(tmp_path):
    db_path = tmp_path / "audit.db"
    await init_db(str(db_path))

    async with aiosqlite.connect(db_path) as db:
        async with db.execute("SELECT value FROM audit_meta WHERE key = ?", ("schema_version",)) as cursor:
            row = await cursor.fetchone()
        async with db.execute("SELECT name FROM sqlite_master WHERE type = 'index' AND name = ?", ("idx_result_ok",)) as cursor:
            index_row = await cursor.fetchone()

    assert row[0] == str(SCHEMA_VERSION)
    assert index_row[0] == "idx_result_ok"
