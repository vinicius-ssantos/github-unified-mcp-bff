import pytest
import respx
import httpx

MCP_BASE = "http://mock-mcp:8000"


@pytest.fixture(autouse=True)
def reset_token_cache():
    """Ensure module-level token cache is cleared between tests."""
    import app.mcp_oauth as m
    m.invalidate()
    yield
    m.invalidate()


def _mock_oauth_flow(
    client_id: str = "test-client",
    code: str = "test-code",
    access_token: str = "test-access-token",
    expires_in: int = 3600,
    authorize_status: int = 302,
):
    """Register the three OAuth endpoints on the active respx mock router."""
    respx.post(f"{MCP_BASE}/oauth/register").mock(
        return_value=httpx.Response(201, json={"client_id": client_id})
    )
    redirect_location = f"http://localhost/callback?code={code}&state=x"
    respx.post(f"{MCP_BASE}/oauth/authorize").mock(
        return_value=httpx.Response(
            authorize_status,
            headers={"location": redirect_location},
        )
    )
    respx.post(f"{MCP_BASE}/oauth/token").mock(
        return_value=httpx.Response(
            200,
            json={"access_token": access_token, "token_type": "bearer", "expires_in": expires_in},
        )
    )


@respx.mock
@pytest.mark.asyncio
async def test_get_mcp_token_returns_access_token():
    from app.mcp_oauth import get_mcp_token

    _mock_oauth_flow()
    token = await get_mcp_token(MCP_BASE, "secret123")
    assert token == "test-access-token"


@respx.mock
@pytest.mark.asyncio
async def test_get_mcp_token_caches_result():
    from app.mcp_oauth import get_mcp_token

    _mock_oauth_flow()
    t1 = await get_mcp_token(MCP_BASE, "secret123")
    t2 = await get_mcp_token(MCP_BASE, "secret123")
    assert t1 == t2
    # register + authorize + token called exactly once despite two get_mcp_token calls
    assert respx.calls.call_count == 3


@respx.mock
@pytest.mark.asyncio
async def test_get_mcp_token_refreshes_after_invalidate():
    from app.mcp_oauth import get_mcp_token, invalidate

    _mock_oauth_flow(access_token="first-token")
    t1 = await get_mcp_token(MCP_BASE, "secret123")
    assert t1 == "first-token"

    invalidate()
    _mock_oauth_flow(access_token="second-token")
    t2 = await get_mcp_token(MCP_BASE, "secret123")
    assert t2 == "second-token"


@respx.mock
@pytest.mark.asyncio
async def test_get_mcp_token_raises_on_bad_authorize():
    from app.mcp_oauth import get_mcp_token

    respx.post(f"{MCP_BASE}/oauth/register").mock(
        return_value=httpx.Response(201, json={"client_id": "c1"})
    )
    # Simulate wrong approval secret — MCP returns 403 JSON instead of redirect
    respx.post(f"{MCP_BASE}/oauth/authorize").mock(
        return_value=httpx.Response(403, json={"error": "access_denied"})
    )
    with pytest.raises(RuntimeError, match="OAuth authorize failed"):
        await get_mcp_token(MCP_BASE, "wrong-secret")
