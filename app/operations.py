import hashlib
import json
import secrets
import time
from dataclasses import asdict, dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.auth import get_current_user
from app.config import Settings, get_settings
from app.rbac import user_role
from app.tool_policy import is_allowed, tool_min_role, tool_policy

router = APIRouter(prefix="/api/operations")

OperationStatus = Literal["previewed", "confirmed", "executed", "failed", "expired", "cancelled"]
OPERATION_TTL_SECONDS = 10 * 60
_SENSITIVE_KEYS = {
    "access_token",
    "authorization",
    "client_secret",
    "confirm",
    "confirm_token",
    "github_token",
    "jwt",
    "mcp_token",
    "password",
    "secret",
    "token",
}


class OperationPreviewRequest(BaseModel):
    tool_name: str = Field(min_length=1)
    arguments: dict = Field(default_factory=dict)
    idempotency_key: str | None = Field(default=None, max_length=200)


@dataclass
class PendingOperation:
    operation_id: str
    tool_name: str
    arguments_hash: str
    arguments_redacted: dict
    requested_by: str
    role: str
    risk_level: str
    status: OperationStatus
    created_at: float
    expires_at: float
    idempotency_key: str | None = None


_PENDING_OPERATIONS: dict[str, PendingOperation] = {}
_IDEMPOTENCY_INDEX: dict[tuple[str, str], str] = {}


def _canonical_json(value: dict) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), default=str)


def _arguments_hash(arguments: dict) -> str:
    return hashlib.sha256(_canonical_json(arguments).encode("utf-8")).hexdigest()


def _is_sensitive_key(key: str) -> bool:
    normalized = key.lower().replace("-", "_")
    return any(marker in normalized for marker in _SENSITIVE_KEYS)


def _redact(value):
    if isinstance(value, dict):
        return {k: "<redacted>" if _is_sensitive_key(k) else _redact(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_redact(item) for item in value]
    return value


def _cleanup_expired(now: float | None = None) -> None:
    current = now or time.time()
    expired_ids = [operation_id for operation_id, operation in _PENDING_OPERATIONS.items() if operation.expires_at <= current]
    for operation_id in expired_ids:
        operation = _PENDING_OPERATIONS.pop(operation_id)
        if operation.idempotency_key:
            _IDEMPOTENCY_INDEX.pop((operation.requested_by, operation.idempotency_key), None)


def _operation_payload(operation: PendingOperation) -> dict:
    payload = asdict(operation)
    payload["created_at"] = int(operation.created_at)
    payload["expires_at"] = int(operation.expires_at)
    return payload


@router.post("/preview")
async def preview_operation(
    body: OperationPreviewRequest,
    request: Request,
    settings: Settings = Depends(get_settings),
):
    _cleanup_expired()
    user_info = get_current_user(request, settings)
    if not user_info:
        raise HTTPException(status_code=401, detail="Not authenticated")

    username = user_info["sub"]
    role = user_role(username, settings, user_info.get("teams", []))
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

    if body.idempotency_key:
        indexed_operation_id = _IDEMPOTENCY_INDEX.get((username, body.idempotency_key))
        if indexed_operation_id:
            existing = _PENDING_OPERATIONS.get(indexed_operation_id)
            if existing and existing.status == "previewed" and existing.expires_at > time.time():
                return _operation_payload(existing)

    now = time.time()
    operation = PendingOperation(
        operation_id=f"op_{secrets.token_urlsafe(18)}",
        tool_name=body.tool_name,
        arguments_hash=_arguments_hash(body.arguments),
        arguments_redacted=_redact(body.arguments),
        requested_by=username,
        role=role,
        risk_level=policy.risk,
        status="previewed",
        created_at=now,
        expires_at=now + OPERATION_TTL_SECONDS,
        idempotency_key=body.idempotency_key,
    )
    _PENDING_OPERATIONS[operation.operation_id] = operation
    if body.idempotency_key:
        _IDEMPOTENCY_INDEX[(username, body.idempotency_key)] = operation.operation_id
    return _operation_payload(operation)
