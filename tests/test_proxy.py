import os

import httpx
import pytest
import respx

os.environ.setdefault("MCP_URL", "http://mock-mcp:8000")
os.environ.setdefault("MCP_TOKEN", "test-token")

from fastapi.testclient import TestClient  # noqa: E402

from app.main import app  # noqa: E402

client = TestClient(app)

MCP_BASE = "http://mock-mcp:8000"
MCP_ENDPOINT = f"{MCP_BASE}/mcp"
MCP_HEALTHZ = f"{MCP_BASE}/healthz"


@respx.mock
def test_healthz_proxies_mcp():
    mcp_health = {
        "ok": True, "service": "github-unified-mcp", "version": "1.31.1",
        "tool_schema_version": "v1.31.1", "commit_sha": "abc123", "uptime_seconds": 1000,
    }
    respx.get(MCP_HEALTHZ).mock(return_value=httpx.Response(200, json=mcp_health))

    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["version"] == "1.31.1"


@respx.mock
def test_healthz_mcp_down():
    respx.get(MCP_HEALTHZ).mock(side_effect=httpx.ConnectError("refused"))

    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is False


@respx.mock
def test_mcp_passthrough_success():
    mcp_response = {"jsonrpc": "2.0", "id": 99, "result": {"tools": [{"name": "server_info"}]}}
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json=mcp_response))

    body = {"jsonrpc": "2.0", "id": 99, "method": "tools/list", "params": {}}
    r = client.post("/mcp", json=body)
    assert r.status_code == 200
    assert r.json()["result"]["tools"][0]["name"] == "server_info"


@respx.mock
def test_mcp_passthrough_injects_auth():
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json={"jsonrpc": "2.0", "id": 1, "result": {}}))

    client.post("/mcp", json={"jsonrpc": "2.0", "id": 1, "method": "tools/list", "params": {}})

    assert respx.calls.last.request.headers["authorization"] == "Bearer test-token"


@respx.mock
def test_call_tool_success():
    mcp_response = {"jsonrpc": "2.0", "id": 1, "result": {"content": [{"type": "text", "text": "{}"}]}}
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(200, json=mcp_response))

    r = client.post("/api/mcp/call", json={"name": "server_info", "arguments": {}})
    assert r.status_code == 200
    assert r.json()["result"]["content"][0]["type"] == "text"


@respx.mock
def test_call_tool_mcp_error():
    respx.post(MCP_ENDPOINT).mock(return_value=httpx.Response(500))

    r = client.post("/api/mcp/call", json={"name": "server_info", "arguments": {}})
    assert r.status_code == 500


@respx.mock
def test_call_tool_mcp_unreachable():
    respx.post(MCP_ENDPOINT).mock(side_effect=httpx.ConnectError("refused"))

    r = client.post("/api/mcp/call", json={"name": "server_info", "arguments": {}})
    assert r.status_code == 502


@respx.mock
def test_call_tool_mcp_timeout():
    respx.post(MCP_ENDPOINT).mock(side_effect=httpx.TimeoutException("timeout"))

    r = client.post("/api/mcp/call", json={"name": "server_info", "arguments": {}})
    assert r.status_code == 504


def test_call_tool_missing_name():
    r = client.post("/api/mcp/call", json={"arguments": {}})
    assert r.status_code == 422
