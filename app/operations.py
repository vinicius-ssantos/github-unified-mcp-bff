import hashlib
import hmac
import json
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.rate_limit import check_rate_limit
from app.rbac import is_allowed, user_role
from app.tool_policy import tool_min_role, tool_policy

router = APIRouter(prefix="/api/operations")

_OPERATION_TTL_SECONDS = 300
_MAX_PENDING_OPERATIONS = 500
_SENSITIVE_KEYS = {"authorization", "code", "password", "secret", "token"}
_OPERATIONS: dict[str, "ControlledOperation"] = {}


class OperationPreviewRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


@dataclass
class ControlledOperation:
    operation_id: str
    tool_name: str
    arguments_hash: str
    arguments_redacted: dict[str, Any]
    requested_by: str
    role: str
    risk_level: str
    min_role: str
    status: str
    created_at: str
    expires_at: str


def _hash_arguments(arguments: dict[str, Any]) -> str:
    serialized = json.dumps(arguments, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(serialized.encode()).hexdigest()[:16]


def _redact(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, item in value.items():
            lowered = str(key).lower()
            if any(sensitive in lowered for sensitive in _SENSITIVE_KEYS):
                redacted[key] = "***REDACTED***"
            else:
                redacted[key] = _redact(item)
        return redacted
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _cleanup_expired(now: float | None = None) -> None:
    current = now if now is not None else time.time()
    expired_ids = [operation_id for operation_id, operation in _OPERATIONS.items() if _parse_ts(operation.expires_at) <= current]
    for operation_id in expired_ids:
        _OPERATIONS.pop(operation_id, None)


def _evict_oldest_if_needed() -> None:
    while len(_OPERATIONS) >= _MAX_PENDING_OPERATIONS:
        oldest_id = min(_OPERATIONS, key=lambda operation_id: _parse_ts(_OPERATIONS[operation_id].created_at))
        _OPERATIONS.pop(oldest_id, None)


def _check_csrf(request: Request, user_info: dict[str, Any]) -> None:
    csrf_in_session = user_info.get("csrf")
    if not csrf_in_session:
        return
    csrf_header = request.headers.get("X-CSRF-Token", "")
    if not hmac.compare_digest(csrf_header, csrf_in_session):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def _check_user_rate_limit(username: str, settings: Settings) -> None:
    if not check_rate_limit(
        f"operations-preview:{username}",
        max_requests=settings.rate_limit_per_user_max,
        window=settings.rate_limit_per_user_window,
    ):
        raise HTTPException(status_code=429, detail="Rate limit exceeded — too many requests")


def _parse_ts(value: str) -> float:
    return datetime.fromisoformat(value).timestamp()


def _operation_response(operation: ControlledOperation) -> dict[str, Any]:
    return asdict(operation)


@router.post("/preview")
async def preview_operation(
    body: OperationPreviewRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    user_info = get_current_user(request, settings)
    if not user_info:
        raise HTTPException(status_code=401, detail="Not authenticated")

    username = user_info["sub"]
    _check_csrf(request, user_info)
    _check_user_rate_limit(username, settings)
    role = user_role(username, settings, user_info.get("teams", []))
    policy = tool_policy(body.tool_name)
    min_role = tool_min_role(body.tool_name)

    if not is_allowed(body.tool_name, role, settings):
        if not policy.known:
            raise HTTPException(
                status_code=403,
                detail=f"Tool '{body.tool_name}' is not known to BFF policy and is blocked",
            )
        raise HTTPException(
            status_code=403,
            detail=f"Role '{role}' cannot preview '{body.tool_name}' — requires '{min_role}'",
        )

    _cleanup_expired()
    _evict_oldest_if_needed()
    now = time.time()
    created_at = datetime.fromtimestamp(now, timezone.utc).isoformat()
    expires_at = datetime.fromtimestamp(now + _OPERATION_TTL_SECONDS, timezone.utc).isoformat()
    operation = ControlledOperation(
        operation_id=f"op_{uuid4().hex}",
        tool_name=body.tool_name,
        arguments_hash=_hash_arguments(body.arguments),
        arguments_redacted=_redact(body.arguments),
        requested_by=username,
        role=role,
        risk_level=policy.risk,
        min_role=min_role,
        status="previewed",
        created_at=created_at,
        expires_at=expires_at,
    )
    _OPERATIONS[operation.operation_id] = operation
    return _operation_response(operation)


@router.get("/{operation_id}")
async def get_operation_preview(
    operation_id: str,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    user_info = get_current_user(request, settings)
    if not user_info:
        raise HTTPException(status_code=401, detail="Not authenticated")

    _cleanup_expired()
    operation = _OPERATIONS.get(operation_id)
    if not operation:
        raise HTTPException(status_code=404, detail="Operation not found or expired")

    username = user_info["sub"]
    role = user_role(username, settings, user_info.get("teams", []))
    if operation.requested_by != username and role != "admin":
        raise HTTPException(status_code=403, detail="Operation belongs to a different user")

    return _operation_response(operation)
