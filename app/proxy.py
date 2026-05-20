import hmac
import json
import time

import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.audit import log_call
from app.auth import get_current_user
from app.config import Settings, get_settings
from app.rate_limit import check_rate_limit
from app.rbac import user_role
from app.tool_policy import is_allowed, tool_min_role, tool_policy

router = APIRouter()


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}


async def _get_auth_headers(settings: Settings) -> dict[str, str]:
    if settings.mcp_oauth_authorization_secret:
        from app.mcp_oauth import get_mcp_token
        token = await get_mcp_token(settings.mcp_url, settings.mcp_oauth_authorization_secret)
        return {"Authorization": f"Bearer {token}"}
    if settings.mcp_token:
        return {"Authorization": f"Bearer {settings.mcp_token}"}
    return {}


def _check_csrf(request: Request, user_info: dict | None) -> None:
    if not user_info:
        return  # anonymous — no session to steal
    csrf_in_session = user_info.get("csrf")
    if not csrf_in_session:
        return  # legacy token without csrf field — skip
    csrf_header = request.headers.get("X-CSRF-Token", "")
    if not hmac.compare_digest(csrf_header, csrf_in_session):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def _check_user_rate_limit(key: str, settings: Settings) -> None:
    if not check_rate_limit(key, max_requests=settings.rate_limit_per_user_max, window=settings.rate_limit_per_user_window):
        raise HTTPException(status_code=429, detail="Rate limit exceeded — too many requests")


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _extract_tool(body: bytes) -> tuple[str, dict, bool]:
    try:
        parsed = json.loads(body)
        method = parsed.get("method", "")
        if method == "tools/call":
            params = parsed.get("params", {})
            return params.get("name", "unknown"), params.get("arguments", {}), True
        return method or "unknown", {}, False
    except Exception:
        return "unknown", {}, False


def _enforce_tool_policy(tool_name: str, role: str, settings: Settings) -> None:
    policy = tool_policy(tool_name)
    if not is_allowed(tool_name, role, settings):
        if not policy.known:
            raise HTTPException(
                status_code=403,
                detail=f"Tool '{tool_name}' is not known to BFF policy and is blocked",
            )
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' cannot call '{tool_name}' — requires '{tool_min_role(tool_name)}'",
        )


async def _forward(
    settings: Settings,
    body: bytes | None = None,
    payload: dict | None = None,
    timeout: float = 30.0,
) -> dict:
    for attempt in range(2):
        auth = await _get_auth_headers(settings)
        headers = {"Content-Type": "application/json", **auth}
        async with httpx.AsyncClient(timeout=timeout) as client:
            try:
                if body is not None:
                    r = await client.post(f"{settings.mcp_url}/mcp", content=body, headers=headers)
                else:
                    r = await client.post(f"{settings.mcp_url}/mcp", json=payload, headers=headers)
                if r.status_code == 401 and attempt == 0 and settings.mcp_oauth_authorization_secret:
                    # Token may have been revoked — invalidate cache and retry once
                    from app.mcp_oauth import invalidate
                    invalidate()
                    continue
                if r.status_code >= 400:
                    raise HTTPException(status_code=r.status_code, detail="MCP server returned error")
                return r.json()
            except HTTPException:
                raise
            except httpx.TimeoutException:
                raise HTTPException(status_code=504, detail="MCP server timeout")
            except httpx.RequestError:
                raise HTTPException(status_code=502, detail="MCP server unreachable")
    raise HTTPException(status_code=401, detail="MCP authentication failed")


@router.get("/healthz")
async def healthz_proxy(settings: Settings = Depends(get_settings)):
    headers = await _get_auth_headers(settings)
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
    tool_name, arguments, is_tool_call = _extract_tool(body)
    user_info = get_current_user(request, settings)
    username = user_info["sub"] if user_info else "anonymous"
    teams = user_info.get("teams", []) if user_info else []
    role = user_role(username, settings, teams) if user_info else "viewer"
    ip = _client_ip(request)

    _check_csrf(request, user_info)
    _check_user_rate_limit(user_info["sub"] if user_info else ip, settings)
    if not settings.allow_raw_mcp_passthrough:
        raise HTTPException(status_code=403, detail="Raw MCP passthrough is disabled")
    if is_tool_call:
        if not settings.allow_raw_mcp_tools_call:
            raise HTTPException(status_code=403, detail="Raw MCP tool execution is disabled")
        _enforce_tool_policy(tool_name, role, settings)

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
    teams = user_info.get("teams", []) if user_info else []
    role = user_role(username, settings, teams) if user_info else "viewer"
    ip = _client_ip(request)

    _check_csrf(request, user_info)
    _check_user_rate_limit(user_info["sub"] if user_info else ip, settings)
    _enforce_tool_policy(body.name, role, settings)

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
