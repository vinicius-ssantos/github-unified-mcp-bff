import hashlib
import hmac
import json
import secrets
import time
from copy import deepcopy
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.audit import log_call
from app.auth import get_current_user
from app.config import Settings, get_settings
from app.rate_limit import check_rate_limit
from app.rbac import user_role
from app.tool_policy import is_allowed, tool_min_role, tool_policy

router = APIRouter(prefix="/api/operations")

_OPERATION_TTL_SECONDS = 15 * 60
_SENSITIVE_KEY_PARTS = ("token", "secret", "password", "authorization", "private_key", "access_key")
OperationStatus = Literal["previewed", "confirmed", "executed", "failed", "expired", "cancelled"]


@dataclass
class StoredOperation:
    operation_id: str
    tool_name: str
    arguments_hash: str
    arguments_redacted: dict[str, Any]
    requested_by: str
    role: str
    risk_level: str
    status: OperationStatus
    created_at: float
    expires_at: float


_OPERATIONS: dict[str, StoredOperation] = {}


class OperationPreviewRequest(BaseModel):
    tool_name: str
    arguments: dict[str, Any] = Field(default_factory=dict)
    idempotency_key: str | None = None


def _client_ip(request: Request) -> str:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else "unknown"


def _check_csrf(request: Request, user_info: dict) -> None:
    csrf_in_session = user_info.get("csrf")
    if not csrf_in_session:
        return
    csrf_header = request.headers.get("X-CSRF-Token", "")
    if not hmac.compare_digest(csrf_header, csrf_in_session):
        raise HTTPException(status_code=403, detail="CSRF validation failed")


def _check_user_rate_limit(key: str, settings: Settings) -> None:
    if not check_rate_limit(key, max_requests=settings.rate_limit_per_user_max, window=settings.rate_limit_per_user_window):
        raise HTTPException(status_code=429, detail="Rate limit exceeded — too many requests")


def _stable_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _arguments_hash(arguments: dict[str, Any]) -> str:
    return hashlib.sha256(_stable_json(arguments).encode("utf-8")).hexdigest()


def _redact_value(value: Any) -> Any:
    if isinstance(value, dict):
        redacted: dict[str, Any] = {}
        for key, nested in value.items():
            normalized = str(key).lower()
            if any(part in normalized for part in _SENSITIVE_KEY_PARTS):
                redacted[key] = "[REDACTED]"
            else:
                redacted[key] = _redact_value(nested)
        return redacted
    if isinstance(value, list):
        return [_redact_value(item) for item in value]
    return value


def _cleanup_expired_operations(now: float) -> None:
    expired = [operation_id for operation_id, op in _OPERATIONS.items() if op.expires_at <= now]
    for operation_id in expired:
        _OPERATIONS.pop(operation_id, None)


def _operation_response(op: StoredOperation) -> dict[str, Any]:
    return {
        "operation_id": op.operation_id,
        "tool_name": op.tool_name,
        "arguments_hash": op.arguments_hash,
        "arguments_redacted": deepcopy(op.arguments_redacted),
        "requested_by": op.requested_by,
        "role": op.role,
        "risk_level": op.risk_level,
        "status": op.status,
        "created_at": datetime.fromtimestamp(op.created_at, timezone.utc).isoformat(),
        "expires_at": datetime.fromtimestamp(op.expires_at, timezone.utc).isoformat(),
        "ttl_seconds": max(0, int(op.expires_at - time.time())),
        "execution_enabled": False,
    }


def _idempotent_operation_id(username: str, idempotency_key: str) -> str:
    digest = hashlib.sha256(f"{username}:{idempotency_key}".encode("utf-8")).hexdigest()[:24]
    return f"op_{digest}"


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
    teams = user_info.get("teams", [])
    role = user_role(username, settings, teams)
    ip = _client_ip(request)
    started = time.monotonic()
    result_ok = True

    try:
        _check_csrf(request, user_info)
        _check_user_rate_limit(username, settings)

        policy = tool_policy(body.tool_name)
        if not is_allowed(body.tool_name, role, settings):
            if not policy.known:
                raise HTTPException(
                    status_code=403,
                    detail=f"Tool '{body.tool_name}' is not known to BFF policy and is blocked",
                )
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role}' cannot preview '{body.tool_name}' — requires '{tool_min_role(body.tool_name)}'",
            )

        now = time.time()
        _cleanup_expired_operations(now)
        operation_id = (
            _idempotent_operation_id(username, body.idempotency_key)
            if body.idempotency_key
            else f"op_{secrets.token_urlsafe(18)}"
        )
        existing = _OPERATIONS.get(operation_id)
        if existing and existing.expires_at > now:
            return _operation_response(existing)

        op = StoredOperation(
            operation_id=operation_id,
            tool_name=body.tool_name,
            arguments_hash=_arguments_hash(body.arguments),
            arguments_redacted=_redact_value(body.arguments),
            requested_by=username,
            role=role,
            risk_level=policy.risk,
            status="previewed",
            created_at=now,
            expires_at=now + _OPERATION_TTL_SECONDS,
        )
        _OPERATIONS[operation_id] = op
        return _operation_response(op)
    except HTTPException:
        result_ok = False
        raise
    finally:
        await log_call(
            settings.audit_db_path,
            username,
            f"operation.preview:{body.tool_name}",
            {"arguments_hash": _arguments_hash(body.arguments)},
            result_ok,
            ip,
            int((time.monotonic() - started) * 1000),
        )
