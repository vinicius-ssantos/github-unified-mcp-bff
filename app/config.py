from functools import lru_cache
from pathlib import Path
from urllib.parse import urlparse

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    # Runtime
    bff_env: str = "development"

    # MCP server
    mcp_url: str
    mcp_token: str = ""
    mcp_oauth_authorization_secret: str = ""
    allowed_origins: str = "http://localhost:5173"
    port: int = 8000

    # Frontend / browser session
    frontend_url: str = "http://localhost:5173"
    cookie_secure: bool = False
    cookie_samesite: str = "lax"
    cookie_domain: str = ""

    # GitHub OAuth (Camada 2)
    github_client_id: str = ""
    github_client_secret: str = ""
    github_callback_url: str = "http://localhost:8000/auth/callback"

    # JWT
    jwt_secret: str = "change-me-in-production"
    jwt_ttl_seconds: int = 3600

    # RBAC — comma-separated GitHub usernames
    rbac_operator_users: str = ""
    rbac_admin_users: str = ""
    # RBAC — comma-separated org/team slugs (e.g. "myorg/ops,myorg/admins")
    rbac_operator_teams: str = ""
    rbac_admin_teams: str = ""

    # Rate limiting — per-user sliding window
    rate_limit_per_user_max: int = 60
    rate_limit_per_user_window: int = 60

    # Tool policy
    block_unknown_tools: bool = True
    allow_raw_mcp_passthrough: bool = True
    allow_raw_mcp_tools_call: bool = True

    # Audit
    audit_backend: str = "sqlite"
    audit_sqlite_persistence: str = "ephemeral"
    audit_db_path: str = "audit.db"
    audit_retention_days: int = 90


_PRIVATE_HOSTS = {"localhost", "127.0.0.1", "::1"}
_PRIVATE_HOST_PREFIXES = ("10.", "192.168.", "169.254.")
_ALLOWED_SAMESITE_VALUES = {"lax", "none", "strict"}
_ALLOWED_AUDIT_BACKENDS = {"sqlite"}
_ALLOWED_AUDIT_SQLITE_PERSISTENCE = {"ephemeral", "persistent"}
_EPHEMERAL_AUDIT_PATHS = {"audit.db", ":memory:"}
_EPHEMERAL_AUDIT_PREFIXES = ("/tmp/", "/var/tmp/")


def is_production(settings: Settings) -> bool:
    return settings.bff_env.lower() == "production"


def _is_private_mcp_host(mcp_url: str) -> bool:
    host = urlparse(mcp_url).hostname or ""
    if host in _PRIVATE_HOSTS:
        return True
    if host.startswith(_PRIVATE_HOST_PREFIXES):
        return True
    if host.startswith("172."):
        parts = host.split(".")
        if len(parts) > 1 and parts[1].isdigit():
            return 16 <= int(parts[1]) <= 31
    return host.startswith(("fc00:", "fe80:"))


def _is_http_url(value: str) -> bool:
    return urlparse(value).scheme in {"http", "https"}


def validate_production_settings(settings: Settings) -> None:
    """Fail fast when production configuration is unsafe."""
    cookie_samesite = settings.cookie_samesite.lower()
    if cookie_samesite not in _ALLOWED_SAMESITE_VALUES:
        raise RuntimeError("COOKIE_SAMESITE must be one of: lax, none, strict")
    if cookie_samesite == "none" and not settings.cookie_secure:
        raise RuntimeError("COOKIE_SECURE must be true when COOKIE_SAMESITE=none")
    if settings.audit_backend not in _ALLOWED_AUDIT_BACKENDS:
        raise RuntimeError("AUDIT_BACKEND must be one of: sqlite")
    if settings.audit_sqlite_persistence not in _ALLOWED_AUDIT_SQLITE_PERSISTENCE:
        raise RuntimeError("AUDIT_SQLITE_PERSISTENCE must be one of: ephemeral, persistent")

    if not is_production(settings):
        return

    errors: list[str] = []
    origins = [origin.strip() for origin in settings.allowed_origins.split(",") if origin.strip()]

    if settings.jwt_secret in ("", "change-me-in-production"):
        errors.append("JWT_SECRET must be set to a strong non-default value in production")
    if not origins:
        errors.append("ALLOWED_ORIGINS must contain at least one explicit origin in production")
    if "*" in origins:
        errors.append("ALLOWED_ORIGINS must not contain '*' in production")
    if not settings.mcp_token and not settings.mcp_oauth_authorization_secret:
        errors.append("MCP_TOKEN or MCP_OAUTH_AUTHORIZATION_SECRET must be configured in production")
    if not settings.mcp_url.startswith("https://"):
        errors.append("MCP_URL must use https:// in production")
    if _is_private_mcp_host(settings.mcp_url):
        errors.append("MCP_URL must not point to localhost or a private network address in production")
    if not _is_http_url(settings.frontend_url):
        errors.append("FRONTEND_URL must be an http(s) URL in production")
    if not settings.frontend_url.startswith("https://"):
        errors.append("FRONTEND_URL must use https:// in production")
    if not settings.cookie_secure:
        errors.append("COOKIE_SECURE must be true in production")
    if settings.audit_backend == "sqlite" and settings.audit_sqlite_persistence != "persistent":
        errors.append("AUDIT_SQLITE_PERSISTENCE must be persistent in production")
    if settings.allow_raw_mcp_passthrough:
        errors.append("ALLOW_RAW_MCP_PASSTHROUGH must be false in production")
    if settings.allow_raw_mcp_tools_call:
        errors.append("ALLOW_RAW_MCP_TOOLS_CALL must be false in production")
    audit_path = settings.audit_db_path.strip()
    audit_path_obj = Path(audit_path)
    if settings.audit_backend == "sqlite" and settings.audit_sqlite_persistence == "persistent":
        if audit_path in _EPHEMERAL_AUDIT_PATHS or audit_path.startswith(_EPHEMERAL_AUDIT_PREFIXES):
            errors.append("AUDIT_DB_PATH must point to persistent storage in production")
        if not audit_path_obj.is_absolute():
            errors.append("AUDIT_DB_PATH should be an absolute persistent path in production")

    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    validate_production_settings(settings)
    return settings
