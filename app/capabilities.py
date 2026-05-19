from fastapi import APIRouter, Depends, Request

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.rbac import user_role

router = APIRouter(prefix="/api")


def _mcp_auth_mode(settings: Settings) -> str:
    if settings.mcp_oauth_authorization_secret:
        return "oauth_service_account"
    if settings.mcp_token:
        return "static_bearer"
    return "none"


def _current_user_payload(request: Request, settings: Settings) -> tuple[bool, dict | None]:
    payload = get_current_user(request, settings)
    if not payload:
        return False, None
    role = user_role(payload["sub"], settings, payload.get("teams", []))
    return True, {
        "login": payload["sub"],
        "name": payload.get("name", payload["sub"]),
        "role": role,
    }


@router.get("/capabilities")
async def capabilities(request: Request, settings: Settings = Depends(get_settings)):
    authenticated, user = _current_user_payload(request, settings)
    return {
        "service": "github-unified-mcp-bff",
        "version": "0.2.0",
        "environment": settings.bff_env,
        "authenticated": authenticated,
        "user": user,
        "auth": {
            "github_oauth_configured": bool(settings.github_client_id),
            "csrf_required": authenticated,
            "cookie_session": True,
            "frontend_url_configured": bool(settings.frontend_url),
            "cookie_samesite": settings.cookie_samesite.lower(),
            "cookie_secure": settings.cookie_secure,
        },
        "mcp": {
            "auth_mode": _mcp_auth_mode(settings),
            "raw_passthrough_enabled": settings.allow_raw_mcp_passthrough,
            "raw_tool_execution_enabled": settings.allow_raw_mcp_tools_call,
            "structured_call_enabled": True,
        },
        "features": {
            "audit": True,
            "audit_protected": True,
            "controlled_operations": False,
            "tool_policy": True,
            "unknown_tools_blocked": settings.block_unknown_tools,
        },
        "limits": {
            "rate_limit_per_user_max": settings.rate_limit_per_user_max,
            "rate_limit_per_user_window": settings.rate_limit_per_user_window,
        },
    }
