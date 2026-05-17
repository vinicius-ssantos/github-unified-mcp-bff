import os

import httpx
import pytest
import respx

os.environ.setdefault("MCP_URL", "http://mock-mcp:8000")
os.environ.setdefault("MCP_TOKEN", "test-token")

from fastapi.testclient import TestClient  # noqa: E402 — env vars must be set first

from app.main import app  # noqa: E402

client = TestClient(app)

MCP_ENDPOINT = "http://mock-mcp:8000/mcp"


def test_healthz():
    r = client.get("/healthz")
    assert r.status_code == 200
    assert r.json()["ok"] is True


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
