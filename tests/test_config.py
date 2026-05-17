import pytest

from app.config import Settings, validate_production_settings


def _prod_settings(**overrides):
    base = {
        "bff_env": "production",
        "mcp_url": "https://github-unified-mcp.onrender.com",
        "mcp_token": "test-token",
        "allowed_origins": "https://frontend.example.com",
        "jwt_secret": "super-secret-value",
    }
    base.update(overrides)
    return Settings(**base)


def test_development_allows_local_defaults():
    settings = Settings(mcp_url="http://localhost:8001")
    validate_production_settings(settings)


def test_production_accepts_safe_config():
    validate_production_settings(_prod_settings())


@pytest.mark.parametrize(
    ("field", "value", "message"),
    [
        ("jwt_secret", "change-me-in-production", "JWT_SECRET"),
        ("jwt_secret", "", "JWT_SECRET"),
        ("allowed_origins", "*", "ALLOWED_ORIGINS"),
        ("allowed_origins", "", "ALLOWED_ORIGINS"),
        ("mcp_url", "http://github-unified-mcp.onrender.com", "MCP_URL must use https"),
        ("mcp_url", "http://localhost:8000", "MCP_URL must use https"),
        ("mcp_url", "https://127.0.0.1:8000", "private network"),
        ("mcp_url", "https://10.0.0.5", "private network"),
        ("mcp_url", "https://172.16.0.5", "private network"),
        ("mcp_url", "https://192.168.0.5", "private network"),
    ],
)
def test_production_rejects_unsafe_values(field, value, message):
    settings = _prod_settings(**{field: value})
    with pytest.raises(RuntimeError, match=message):
        validate_production_settings(settings)


def test_production_requires_mcp_auth():
    settings = _prod_settings(mcp_token="", mcp_oauth_authorization_secret="")
    with pytest.raises(RuntimeError, match="MCP_TOKEN or MCP_OAUTH_AUTHORIZATION_SECRET"):
        validate_production_settings(settings)


def test_production_accepts_mcp_oauth_secret_without_static_token():
    settings = _prod_settings(mcp_token="", mcp_oauth_authorization_secret="approval-secret")
    validate_production_settings(settings)
