import httpx
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter()


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}


def _auth_headers(settings: Settings) -> dict[str, str]:
    if settings.mcp_token:
        return {"Authorization": f"Bearer {settings.mcp_token}"}
    return {}


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
    headers = {"Content-Type": "application/json", **_auth_headers(settings)}
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
            r = await client.post(f"{settings.mcp_url}/mcp", content=body, headers=headers)
            if r.status_code >= 400:
                raise HTTPException(status_code=r.status_code, detail="MCP server returned error")
            return r.json()
        except HTTPException:
            raise
        except httpx.TimeoutException:
            raise HTTPException(status_code=504, detail="MCP server timeout")
        except httpx.RequestError:
            raise HTTPException(status_code=502, detail="MCP server unreachable")


@router.post("/api/mcp/call")
async def call_tool(body: ToolCallRequest, settings: Settings = Depends(get_settings)):
    headers = {"Content-Type": "application/json", **_auth_headers(settings)}
    payload = {
        "jsonrpc": "2.0",
        "id": 1,
        "method": "tools/call",
        "params": {"name": body.name, "arguments": body.arguments},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        try:
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
