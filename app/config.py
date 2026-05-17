from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    mcp_url: str
    mcp_token: str = ""
    allowed_origins: str = "http://localhost:5173"
    port: int = 8000


@lru_cache
def get_settings() -> Settings:
    return Settings()
