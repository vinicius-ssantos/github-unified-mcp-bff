from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jose import jwt


def _session_cookie(username: str = "operator", csrf: str = "csrf-token", teams: list[str] | None = None) -> str:
    from app.config import get_settings

    settings = get_settings()
    exp = datetime.now(timezone.utc) + timedelta(seconds=3600)
    return jwt.encode(
        {"sub": username, "name": username, "teams": teams or [], "csrf": csrf, "exp": exp},
        settings.jwt_secret,
        algorithm="HS256",
    )


def _client():
    from app.main import app

    return TestClient(app)


def test_preview_requires_authentication():
    with _client() as client:
        response = client.post("/api/operations/preview", json={"tool_name": "issue_create", "arguments": {}})

    assert response.status_code == 401
    assert response.json()["detail"] == "Not authenticated"


def test_viewer_cannot_preview_medium_risk_tool():
    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "issue_create", "arguments": {"title": "Test"}},
            cookies={"bff_session": _session_cookie("viewer")},
        )

    assert response.status_code == 403
    assert "requires 'operator'" in response.json()["detail"]


def test_operator_can_preview_medium_risk_tool(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator")

    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "issue_create", "arguments": {"title": "Test"}},
            cookies={"bff_session": _session_cookie("operator")},
        )

    assert response.status_code == 200
    body = response.json()
    assert body["operation_id"].startswith("op_")
    assert body["tool_name"] == "issue_create"
    assert body["requested_by"] == "operator"
    assert body["role"] == "operator"
    assert body["risk_level"] == "medium"
    assert body["status"] == "previewed"
    assert len(body["arguments_hash"]) == 64
    assert body["arguments_redacted"] == {"title": "Test"}
    assert body["expires_at"] > body["created_at"]


def test_operator_cannot_preview_high_risk_tool(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator")

    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "pr_merge", "arguments": {"pull_number": 1}},
            cookies={"bff_session": _session_cookie("operator")},
        )

    assert response.status_code == 403
    assert "requires 'admin'" in response.json()["detail"]


def test_admin_can_preview_high_risk_tool(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_admin_users", "admin")

    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "pr_merge", "arguments": {"pull_number": 1}},
            cookies={"bff_session": _session_cookie("admin")},
        )

    assert response.status_code == 200
    assert response.json()["risk_level"] == "high"
    assert response.json()["role"] == "admin"


def test_preview_redacts_sensitive_arguments(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator")

    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={
                "tool_name": "issue_create",
                "arguments": {
                    "title": "Safe",
                    "token": "secret-value",
                    "nested": {"client_secret": "hidden", "visible": "ok"},
                },
            },
            cookies={"bff_session": _session_cookie("operator")},
        )

    assert response.status_code == 200
    assert response.json()["arguments_redacted"] == {
        "title": "Safe",
        "token": "<redacted>",
        "nested": {"client_secret": "<redacted>", "visible": "ok"},
    }
    assert response.json()["arguments_hash"] != "secret-value"


def test_preview_idempotency_returns_same_operation(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator")
    payload = {
        "tool_name": "issue_create",
        "arguments": {"title": "Idempotent"},
        "idempotency_key": "same-request",
    }

    with _client() as client:
        first = client.post(
            "/api/operations/preview",
            json=payload,
            cookies={"bff_session": _session_cookie("operator")},
        )
        second = client.post(
            "/api/operations/preview",
            json=payload,
            cookies={"bff_session": _session_cookie("operator")},
        )

    assert first.status_code == 200
    assert second.status_code == 200
    assert second.json()["operation_id"] == first.json()["operation_id"]
    assert second.json()["arguments_hash"] == first.json()["arguments_hash"]


def test_unknown_tool_preview_is_blocked(monkeypatch):
    from app.config import get_settings

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_admin_users", "admin")

    with _client() as client:
        response = client.post(
            "/api/operations/preview",
            json={"tool_name": "unknown_future_tool", "arguments": {}},
            cookies={"bff_session": _session_cookie("admin")},
        )

    assert response.status_code == 403
    assert "not known to BFF policy" in response.json()["detail"]
