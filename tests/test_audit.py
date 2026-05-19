import aiosqlite
import pytest
from fastapi.testclient import TestClient

from app.audit import SCHEMA_VERSION, init_db


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


def test_audit_returns_empty_initially(client):
    r = client.get("/api/audit")
    assert r.status_code == 200
    data = r.json()
    assert "events" in data
    assert "total" in data


def test_audit_pagination_params(client):
    r = client.get("/api/audit?limit=10&offset=0")
    assert r.status_code == 200


def test_audit_filter_by_tool(client):
    r = client.get("/api/audit?tool=server_info")
    assert r.status_code == 200
    for event in r.json()["events"]:
        assert "server_info" in event["tool"]


def test_audit_filter_by_user(client):
    r = client.get("/api/audit?user=anonymous")
    assert r.status_code == 200


def test_audit_limit_max(client):
    r = client.get("/api/audit?limit=201")
    assert r.status_code == 422


def test_audit_health_endpoint(client):
    r = client.get("/api/audit/health")
    assert r.status_code == 200
    data = r.json()
    assert data["ok"] is True
    assert data["backend"] == "sqlite"
    assert data["schema_version"] == str(SCHEMA_VERSION)
    assert "events_total" in data
    assert "retention_days" in data


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
