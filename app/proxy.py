import json
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.audit import log_call
from app.auth import get_current_user
from app.config import Settings, get_settings
from app.rbac import is_allowed, user_role

router = APIRouter()


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}


def _auth_headers(settings: Settings) -> dict[str, str]:
    if settings.mcp_token:
        return {"Authorization": f"Bearer {settings.mcp_token}"}
    return {}


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_tool(body: bytes) -> tuple[str, dict]:
    try:
        parsed = json.loads(body)
        method = parsed.get("method", "")
        if method == "tools/call":
            params = parsed.get("params", {})
            return params.get("name", "unknown"), params.get("arguments", {})
        return method or "unknown", {}
    except Exception:
        return "unknown", {}


async def _forward(
    settings: Settings,
    body: bytes | None = None,
    payload: dict | None = None,
    timeout: float = 30.0,
) -> dict:
    headers = {"Content-Type": "application/json", **_auth_headers(settings)}
    async with httpx.AsyncClient(timeout=timeout) as client:
        try:
            if body is not None:
                r = await client.post(f"{settings.mcp_url}/mcp", content=body, headers=headers)
            else:
                r = await client.post(f"{settings.mcp_url}/mcp", json=payload, headers=headers)
            if r.status_code >= 400:
                raise HTTPException(status_code=r.status_code, detail="MCP server returned error")
            return r.json()
        except HTTPException:
            raise
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="MCP server timeout")
        except httpx.RequestError:
            raise HTTPException(status_code=502, detail="MCP server unreachable")


@router.get("/healthz")
async def healthz_proxy(settings: Settings = Depends(get_settings)):
    headers = _auth_headers(settings)
    async with httpx.AsyncClient(timeout=5.0) as client:
        try:
            r = await client.get(f"{settings.mcp_url}/healthz", headers=headers)
            if r.status_code == 200:
                return r.json()
        except Exception:
            pass
    return {"ok": False, "service": "github-unified-mcp-bff", "error": "MCP unreachable"}


@router.post("/mcp")
async def mcp_passthrough(request: Request, settings: Settings = Depends(get_settings)):
    body = await request.body()
    tool_name, arguments = _extract_tool(body)
    user_info = get_current_user(request, settings)
    username = user_info["sub"] if user_info else "anonymous"
    role = user_role(username, settings) if user_info else "viewer"
    ip = _client_ip(request)
    start = time.monotonic()
    result_ok = True
    try:
        result = await _forward(settings, body=body)
        return result
    except HTTPException:
        result_ok = False
        raise
    finally:
        await log_call(
            settings.audit_db_path, username, tool_name, arguments,
            result_ok, ip, int((time.monotonic() - start) * 1000),
        )


@router.post("/api/mcp/call")
async def call_tool(body: ToolCallRequest, request: Request, settings: Settings = Depends(get_settings)):
    user_info = get_current_user(request, settings)
    username = user_info["sub"] if user_info else "anonymous"
    role = user_role(username, settings) if user_info else "viewer"
    ip = _client_ip(request)

    # RBAC gate — only enforced when OAuth is configured
    if settings.github_client_id and not is_allowed(body.name, role):
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' cannot call '{body.name}' — requires '{__import__('app.rbac', fromlist=['tool_min_role']).tool_min_role(body.name)}'",
        )

    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": body.name, "arguments": body.arguments},
    }
    start = time.monotonic()
    result_ok = True
    try:
        result = await _forward(settings, payload=payload)
        return result
    except HTTPException:
        result_ok = False
        raise
    finally:
        await log_call(
            settings.audit_db_path, username, body.name, body.arguments,
            result_ok, ip, int((time.monotonic() - start) * 1000),
        )
