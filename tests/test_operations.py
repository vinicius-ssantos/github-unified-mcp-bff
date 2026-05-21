from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
from jose import jwt



def _session_token(settings, sub="testuser", name="Test User", teams=None):
    exp = datetime.now(timezone.utc) + timedelta(seconds=3600)
    return jwt.encode(
        {
            "sub": sub,
            "name": name,
            "teams": teams or [],
            "csrf": "csrf-token",
            "exp": exp,
        },
        settings.jwt_secret,
        algorithm="HS256",
    )


def _set_session(client, settings, sub="testuser", teams=None):
    client.cookies.set("bff_session", _session_token(settings, sub=sub, teams=teams))



def test_operation_preview_requires_authentication():
    from app.main import app

    with TestClient(app) as client:
        client.cookies.clear()
        r = client.post("/api/operations/preview", json={"tool_name": "issue_create", "arguments": {}})

    assert r.status_code == 401



def test_viewer_cannot_preview_medium_risk_operation(monkeypatch):
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "")
    monkeypatch.setattr(settings, "rbac_admin_users", "")

    with TestClient(app) as client:
        _set_session(client, settings, sub="viewer-user")
        r = client.post("/api/operations/preview", json={"tool_name": "issue_create", "arguments": {}})

    assert r.status_code == 403
    assert "requires 'operator'" in r.json()["detail"]



def test_operator_can_preview_medium_risk_operation(monkeypatch):
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-user")

    with TestClient(app) as client:
        _set_session(client, settings, sub="operator-user")
        r = client.post(
            "/api/operations/preview",
            json={
                "tool_name": "issue_create",
                "arguments": {"title": "Test issue", "body": "safe"},
            },
        )

    assert r.status_code == 200
    data = r.json()
    assert data["operation_id"].startswith("op_")
    assert data["tool_name"] == "issue_create"
    assert data["requested_by"] == "operator-user"
    assert data["role"] == "operator"
    assert data["risk_level"] == "medium"
    assert data["min_role"] == "operator"
    assert data["status"] == "previewed"
    assert data["arguments_redacted"] == {"title": "Test issue", "body": "safe"}
    assert len(data["arguments_hash"]) == 16



def test_operator_cannot_preview_high_risk_operation(monkeypatch):
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-high-user")
    monkeypatch.setattr(settings, "rbac_admin_users", "")

    with TestClient(app) as client:
        _set_session(client, settings, sub="operator-high-user")
        r = client.post("/api/operations/preview", json={"tool_name": "pr_merge", "arguments": {}})

    assert r.status_code == 403
    assert "requires 'admin'" in r.json()["detail"]



def test_admin_can_preview_high_risk_operation_and_redacts_sensitive_arguments(monkeypatch):
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_admin_users", "admin-user")

    with TestClient(app) as client:
        _set_session(client, settings, sub="admin-user")
        r = client.post(
            "/api/operations/preview",
            json={
                "tool_name": "pr_merge",
                "arguments": {
                    "pull_number": 23,
                    "token": "secret-token",
                    "nested": {"authorization_header": "Bearer x"},
                },
            },
        )

    assert r.status_code == 200
    data = r.json()
    assert data["risk_level"] == "high"
    assert data["min_role"] == "admin"
    assert data["arguments_redacted"]["pull_number"] == 23
    assert data["arguments_redacted"]["token"] == "***REDACTED***"
    assert data["arguments_redacted"]["nested"]["authorization_header"] == "***REDACTED***"



def test_unknown_tool_preview_is_blocked(monkeypatch):
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_admin_users", "admin-unknown-user")
    monkeypatch.setattr(settings, "block_unknown_tools", True)

    with TestClient(app) as client:
        _set_session(client, settings, sub="admin-unknown-user")
        r = client.post("/api/operations/preview", json={"tool_name": "new_unknown_tool", "arguments": {}})

    assert r.status_code == 403
    assert "not known to BFF policy" in r.json()["detail"]



def test_operation_preview_can_be_loaded_by_requester(monkeypatch):
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "operator-load-user")

    with TestClient(app) as client:
        _set_session(client, settings, sub="operator-load-user")
        created = client.post("/api/operations/preview", json={"tool_name": "issue_create", "arguments": {}})
        operation_id = created.json()["operation_id"]
        loaded = client.get(f"/api/operations/{operation_id}")

    assert loaded.status_code == 200
    assert loaded.json()["operation_id"] == operation_id



def test_operation_preview_cannot_be_loaded_by_different_non_admin(monkeypatch):
    from app.config import get_settings
    from app.main import app

    settings = get_settings()
    monkeypatch.setattr(settings, "rbac_operator_users", "owner-user,other-user")
    monkeypatch.setattr(settings, "rbac_admin_users", "")

    with TestClient(app) as client:
        _set_session(client, settings, sub="owner-user")
        created = client.post("/api/operations/preview", json={"tool_name": "issue_create", "arguments": {}})
        operation_id = created.json()["operation_id"]

        client.cookies.clear()
        _set_session(client, settings, sub="other-user")
        loaded = client.get(f"/api/operations/{operation_id}")

    assert loaded.status_code == 403
    assert "different user" in loaded.json()["detail"]
