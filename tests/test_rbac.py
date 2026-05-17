from app.config import get_settings
from app.rbac import is_allowed, tool_min_role, user_role


def _settings():
    return get_settings()


def test_user_role_by_username_admin():
    s = _settings()
    assert user_role("admin-user", s) == "admin"


def test_user_role_by_username_operator():
    s = _settings()
    assert user_role("operator-user", s) == "operator"


def test_user_role_viewer_default():
    s = _settings()
    assert user_role("random-user", s) == "viewer"


def test_user_role_by_admin_team():
    s = _settings()
    assert user_role("any-user", s, teams=["myorg/admins"]) == "admin"


def test_user_role_by_operator_team():
    s = _settings()
    assert user_role("any-user", s, teams=["myorg/ops"]) == "operator"


def test_user_role_team_does_not_override_to_lower():
    # Username is admin, even if no team matches — should stay admin
    s = _settings()
    assert user_role("admin-user", s, teams=[]) == "admin"


def test_tool_min_role_high():
    assert tool_min_role("pr_merge") == "admin"
    assert tool_min_role("git_update_ref") == "admin"


def test_tool_min_role_medium():
    assert tool_min_role("pr_create") == "operator"
    assert tool_min_role("branch_create") == "operator"


def test_tool_min_role_low():
    assert tool_min_role("repo_get") == "viewer"
    assert tool_min_role("server_info") == "viewer"


def test_is_allowed_viewer_can_read():
    assert is_allowed("repo_get", "viewer") is True


def test_is_allowed_viewer_blocked_on_write():
    assert is_allowed("pr_create", "viewer") is False


def test_is_allowed_operator_can_write():
    assert is_allowed("pr_create", "operator") is True


def test_is_allowed_operator_blocked_on_high():
    assert is_allowed("pr_merge", "operator") is False


def test_is_allowed_admin_can_do_all():
    assert is_allowed("pr_merge", "admin") is True
    assert is_allowed("git_update_ref", "admin") is True
