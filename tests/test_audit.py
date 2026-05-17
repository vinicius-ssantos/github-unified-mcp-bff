import pytest
from fastapi.testclient import TestClient


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
