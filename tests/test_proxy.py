from unittest.mock import AsyncMock

import httpx
import pytest
import respx

from fastapi.testclient import TestClient

MCP_BASE = "http://mock-mcp:8000"
MCP_ENDPOINT = f"{MCP_BASE}/mcp"
MCP_HEALTHZ = f"{MCP_BASE}/healthz"


@pytest.fixture(scope="module")
def client():
    from app.main import app

    with TestClient(app) as c:
        yield c


@pytest.fixture(autouse=True)
def mock_audit(monkeypatch):
    monkeypatch.setattr("app.proxy.log_call", AsyncMock())


# ── healthz ───────────────────────────────────────────────────────────────────

@respx.mock
def test_healthz_proxies_mcp(client):
    mcp_health = {
        "ok": True,
        "service": "github-unified-mcp",
        "version": "1.31.1",
        "tool_schema_version": "v1.31.1",
        "commit_sha": "abc123",
        "uptime_seconds": 1000,
    }
    respx.get(MCP_HEALTHZ).mock(return_value=httpx.Response(200, json=mcp_health))
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["version"] == "1.31.1"


@respx.mock
def test_healthz_mcp_down(client):
    respx.get(MCP_HEALTHZ).mock(side_effect=httpx.ConnectError("refused"))
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is False


# ── /mcp passthrough ──────────────────────────────────────────────────────────

@respx.mock
def test_mcp_passthrough_success(client):
    mcp_response = {"jsonrpc": "2.0", "id": 99, "result": {"tools": [{"name": "server_info"}]}}
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json=mcp_response))
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}})
    assert r.status_code == 200
    assert r.json()["result"]["tools"][0]["name"] == "server_info"


@respx.mock
def test_mcp_passthrough_injects_auth(client):
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}))
    client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert respx.calls.last.request.headers["authorization"] == "Bearer test-token"


@respx.mock
def test_mcp_passthrough_timeout(client):
    respx.post(MCP_ENDPOINT).mock(side_effect=httpx.TimeoutException("timeout"))
    r = client.post("/mcp", json={})
    assert r.status_code == 504


@respx.mock
def test_mcp_passthrough_unreachable(client):
    respx.post(MCP_ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))
    r = client.post("/mcp", json={})
    assert r.status_code == 502


@respx.mock
def test_mcp_raw_tools_call_low_risk_allowed(client):
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}))
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "server_info", "arguments": {}},
        },
    )
    assert r.status_code == 200


def test_mcp_raw_tools_call_write_blocked_for_viewer(client):
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "pr_create", "arguments": {}},
        },
    )
    assert r.status_code == 403
    assert "requires 'operator'" in r.json()["detail"]


def test_mcp_raw_tools_call_unknown_blocked(client):
    r = client.post(
        "/mcp",
        json={
            "jsonrpc": "2.0",
            "id": 1,
            "method": "tools/call",
            "params": {"name": "new_runtime_tool_not_in_bff_policy", "arguments": {}},
        },
    )
    assert r.status_code == 403
    assert "not known to BFF policy" in r.json()["detail"]


# ── /api/mcp/call ─────────────────────────────────────────────────────────────

@respx.mock
def test_call_tool_success(client):
    mcp_response = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "{}"}]}}
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json=mcp_response))
    r = client.post("/api/mcp/call", json={"name": "server_info", "arguments": {}})
    assert r.status_code == 200


@respx.mock
def test_call_tool_mcp_error(client):
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(500))
    r = client.post("/api/mcp/call", json={"name": "server_info", "arguments": {}})
    assert r.status_code == 500


@respx.mock
def test_call_tool_mcp_timeout(client):
    respx.post(MCP_ENDPOINT).mock(side_effect=httpx.TimeoutException("timeout"))
    r = client.post("/api/mcp/call", json={"name": "server_info", "arguments": {}})
    assert r.status_code == 504


@respx.mock
def test_call_tool_mcp_unreachable(client):
    respx.post(MCP_ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))
    r = client.post("/api/mcp/call", json={"name": "server_info", "arguments": {}})
    assert r.status_code == 502


def test_call_tool_missing_name(client):
    r = client.post("/api/mcp/call", json={"arguments": {}})
    assert r.status_code == 422


def test_call_tool_write_blocked_for_viewer(client):
    r = client.post("/api/mcp/call", json={"name": "pr_create", "arguments": {}})
    assert r.status_code == 403
    assert "requires 'operator'" in r.json()["detail"]


def test_call_tool_unknown_blocked(client):
    r = client.post("/api/mcp/call", json={"name": "new_runtime_tool_not_in_bff_policy", "arguments": {}})
    assert r.status_code == 403
    assert "not known to BFF policy" in r.json()["detail"]


# ── CSRF ─────────────────────────────────────────────────────────────────────

@respx.mock
def test_mcp_anonymous_no_csrf_required(client):
    """Anonymous requests bypass CSRF check."""
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}))
    r = client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})
    assert r.status_code == 200


@respx.mock
def test_mcp_authenticated_valid_csrf(client):
    """Authenticated request with matching X-CSRF-Token passes."""
    from datetime import datetime, timezone, timedelta
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(seconds=3600)
    csrf_val = "test-csrf-token-abc"
    token = jwt.encode(
        {"sub": "testuser", "name": "Test", "csrf": csrf_val, "exp": exp},
        settings.jwt_secret,
        algorithm="HS256",
    )
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}))
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        cookies={"bff_session": token},
        headers={"X-CSRF-Token": csrf_val},
    )
    assert r.status_code == 200


@respx.mock
def test_mcp_authenticated_wrong_csrf_rejected(client):
    """Authenticated request with wrong X-CSRF-Token is rejected."""
    from datetime import datetime, timezone, timedelta
    from jose import jwt
    from app.config import get_settings

    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(seconds=3600)
    token = jwt.encode(
        {"sub": "testuser", "name": "Test", "csrf": "correct-csrf", "exp": exp},
        settings.jwt_secret,
        algorithm="HS256",
    )
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json={}))
    r = client.post(
        "/mcp",
        json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}},
        cookies={"bff_session": token},
        headers={"X-CSRF-Token": "wrong-csrf"},
    )
    assert r.status_code == 403


# ── Rate limit ────────────────────────────────────────────────────────────────

def test_rate_limit_check_function():
    from app.rate_limit import _SlidingWindow

    w = _SlidingWindow()
    for _ in range(5):
        assert w.is_allowed("test-key", max_requests=5, window=60) is True
    assert w.is_allowed("test-key", max_requests=5, window=60) is False
