from functools import lru_cache
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

    # Audit
    audit_db_path: str = "audit.db"
    audit_retention_days: int = 90


_PRIVATE_HOSTS = {"localhost", "127.0.0.1", "::1"}
_PRIVATE_HOST_PREFIXES = ("10.", "192.168.", "169.254.")


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


def validate_production_settings(settings: Settings) -> None:
    """Fail fast when production configuration is unsafe."""
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

    if errors:
        raise RuntimeError("Unsafe production configuration: " + "; ".join(errors))


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    validate_production_settings(settings)
    return settings
