import httpx
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.config import Settings, get_settings

router = APIRouter()


class ToolCallRequest(BaseModel):
    name: str
    arguments: dict = {}


@router.post("/api/mcp/call")
async def call_tool(body: ToolCallRequest, settings: Settings = Depends(get_settings)):
    headers: dict[str, str] = {"Content-Type": "application/json"}
    if settings.mcp_token:
        headers["Authorization"] = f"Bearer {settings.mcp_token}"

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
