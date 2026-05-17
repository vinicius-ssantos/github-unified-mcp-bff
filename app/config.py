from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

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

    # Audit
    audit_db_path: str = "audit.db"
    audit_retention_days: int = 90


@lru_cache
def get_settings() -> Settings:
    return Settings()
