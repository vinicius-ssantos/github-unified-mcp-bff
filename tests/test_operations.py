from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jose import jwt


def _session_cookie(username: str, csrf: str = "csrf-token", teams: list[str] | None = None) -> dict[str, str]:
    from app.config import get_settings

    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(seconds=3600)
    token = jwt.encode(
        {
            "sub": username,
            "name": username,
            "teams": teams or [],
            "csrf": csrf,
            "exp": exp,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )
    return {"bff_session": token}


def _client():
    from app.main import app

    return TestClient(app)


def test_preview_requires_authentication():
    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "issue_create", "arguments": {"title": "Test"}},
        )

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_viewer_cannot_preview_medium_risk_tool():
    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "issue_create", "arguments": {"title": "Test"}},
            cookies=_session_cookie("viewer-user"),
        )

    assert response.status_code == 403
    assert "requires 'operator'" in response.json()["detail"]


def test_operator_can_preview_medium_risk_tool_and_arguments_are_redacted(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-user")

    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={
                "tool_name": "issue_create",
                "arguments": {
                    "title": "Test issue",
                    "body": "Visible body",
                    "metadata": {"access_token": "secret-token", "nested": ["safe"]},
                },
            },
            cookies=_session_cookie("operator-user"),
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["operation_id"].startswith("op_")
    assert payload["tool_name"] == "issue_create"
    assert payload["risk_level"] == "medium"
    assert payload["role"] == "operator"
    assert payload["status"] == "previewed"
    assert len(payload["arguments_hash"]) == 64
    assert payload["arguments_redacted"] == {
        "title": "Test issue",
        "body": "Visible body",
        "metadata": {"access_token": "<redacted>", "nested": ["safe"]},
    }
    assert payload["expires_at"] > payload["created_at"]


def test_operator_cannot_preview_high_risk_tool(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-user")

    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "pr_merge", "arguments": {"pull_number": 1}},
            cookies=_session_cookie("operator-user"),
        )

    assert response.status_code == 403
    assert "requires 'admin'" in response.json()["detail"]


def test_admin_can_preview_high_risk_tool(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_admin_users", "admin-user")

    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "pr_merge", "arguments": {"pull_number": 1}},
            cookies=_session_cookie("admin-user"),
        )

    payload = response.json()
    assert response.status_code == 200
    assert payload["tool_name"] == "pr_merge"
    assert payload["risk_level"] == "high"
    assert payload["role"] == "admin"


def test_unknown_tool_preview_is_blocked(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_admin_users", "admin-user")

    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "new_runtime_tool", "arguments": {}},
            cookies=_session_cookie("admin-user"),
        )

    assert response.status_code == 403
    assert "not known to BFF policy" in response.json()["detail"]


def test_preview_idempotency_returns_existing_operation(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-user")

    body = {
        "tool_name": "issue_create",
        "arguments": {"title": "Test issue"},
        "idempotency_key": "idem-123",
    }
    with _client() as client:
        first = client.post(
            "/api/operations/preview",
            json=body,
            cookies=_session_cookie("operator-user"),
        )
        second = client.post(
            "/api/operations/preview",
            json=body,
            cookies=_session_cookie("operator-user"),
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert first.json()["operation_id"] == second.json()["operation_id"]
    assert first.json()["arguments_hash"] == second.json()["arguments_hash"]
