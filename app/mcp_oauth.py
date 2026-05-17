"""Service-account OAuth token manager for BFF → MCP connection.

Flow (on first call or after expiry):
  1. POST /oauth/register  — dynamic client registration
  2. POST /oauth/authorize — PKCE + owner approval secret in one shot
  3. POST /oauth/token     — exchange code for access_token

Token is cached in memory and refreshed 60 s before expiry.
Requires MCP_OAUTH_AUTHORIZATION_SECRET (the value set as
MCP_OAUTH_AUTHORIZATION_SECRET on the MCP server).
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import logging
import secrets
import time
from urllib.parse import parse_qs, urlparse

import httpx

_log = logging.getLogger("bff.mcp_oauth")

_access_token: str | None = None
_token_expiry: float = 0.0
_refresh_lock = asyncio.Lock()

_REFRESH_BUFFER = 60


def _pkce_pair() -> tuple[str, str]:
    verifier = secrets.token_urlsafe(64)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return verifier, challenge


async def _fetch_token(mcp_url: str, approval_secret: str) -> tuple[str, float]:
    redirect_uri = "http://localhost/callback"
    async with httpx.AsyncClient(timeout=15.0) as client:
        # 1. Dynamic client registration
        reg = await client.post(
            f"{mcp_url}/oauth/register",
            json={"redirect_uris": [redirect_uri], "token_endpoint_auth_method": "none"},
        )
        reg.raise_for_status()
        client_id = reg.json()["client_id"]

        # 2. Authorization code — PKCE + owner approval in a single POST
        verifier, challenge = _pkce_pair()
        auth = await client.post(
            f"{mcp_url}/oauth/authorize",
            data={
                "response_type": "code",
                "client_id": client_id,
                "redirect_uri": redirect_uri,
                "scope": "mcp",
                "code_challenge": challenge,
                "code_challenge_method": "S256",
                "approval": approval_secret,
            },
            follow_redirects=False,
        )
        if auth.status_code not in (301, 302):
            raise RuntimeError(
                f"OAuth authorize failed ({auth.status_code}): {auth.text[:300]}"
            )

        location = auth.headers.get("location", "")
        code = parse_qs(urlparse(location).query).get("code", [None])[0]
        if not code:
            raise RuntimeError(f"No code in redirect: {location[:300]}")

        # 3. Token exchange
        token_resp = await client.post(
            f"{mcp_url}/oauth/token",
            data={
                "grant_type": "authorization_code",
                "code": code,
                "redirect_uri": redirect_uri,
                "client_id": client_id,
                "code_verifier": verifier,
            },
        )
        token_resp.raise_for_status()
        data = token_resp.json()

    access_token: str = data["access_token"]
    expires_in = int(data.get("expires_in", 3600))
    return access_token, time.monotonic() + expires_in


async def get_mcp_token(mcp_url: str, approval_secret: str) -> str:
    """Return a valid MCP OAuth access token, refreshing proactively before expiry."""
    global _access_token, _token_expiry

    if _access_token and time.monotonic() < _token_expiry - _REFRESH_BUFFER:
        return _access_token

    async with _refresh_lock:
        # Double-checked locking after acquiring lock
        if _access_token and time.monotonic() < _token_expiry - _REFRESH_BUFFER:
            return _access_token

        _log.info("Acquiring MCP OAuth access token")
        token, expiry = await _fetch_token(mcp_url, approval_secret)
        _access_token = token
        _token_expiry = expiry
        _log.info("MCP OAuth token acquired, valid for %.0fs", expiry - time.monotonic())
        return token


def invalidate() -> None:
    """Force re-authentication on next call (useful for 401 retry logic)."""
    global _access_token, _token_expiry
    _access_token = None
    _token_expiry = 0.0
