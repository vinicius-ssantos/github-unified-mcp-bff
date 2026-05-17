import logging
import re
from contextlib import asynccontextmanager
from urllib.parse import urlparse

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.audit import cleanup_old_events, init_db, router as audit_router
from app.auth import router as auth_router
from app.config import get_settings
from app.middleware import SecurityHeadersMiddleware
from app.proxy import router as proxy_router

_settings = get_settings()
_log = logging.getLogger("bff.startup")

_PRIVATE_IP_PATTERNS = [
    r"^10\.", r"^172\.(1[6-9]|2[0-9]|3[01])\.", r"^192\.168\.",
    r"^169\.254\.", r"^127\.", r"^::1$", r"^fc00:", r"^fe80:",
]


def _warn_if_ssrf_risk(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        _log.warning("MCP_URL scheme is not http/https: %s", url)
        return
    host = parsed.hostname or ""
    if host == "localhost":
        _log.warning("MCP_URL points to localhost — acceptable in dev, risky in production")
        return
    for pattern in _PRIVATE_IP_PATTERNS:
        if re.match(pattern, host):
            _log.warning("MCP_URL points to a private network address (%s) — verify this is intentional", host)
            return


@asynccontextmanager
async def lifespan(app: FastAPI):
    _warn_if_ssrf_risk(_settings.mcp_url)
    await init_db(_settings.audit_db_path)
    await cleanup_old_events(_settings.audit_db_path, _settings.audit_retention_days)
    yield


app = FastAPI(title="github-unified-mcp-bff", version="0.2.0", lifespan=lifespan)

app.add_middleware(SecurityHeadersMiddleware)
app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _settings.allowed_origins.split(",")],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(proxy_router)
app.include_router(auth_router)
app.include_router(audit_router)
