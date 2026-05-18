from app.config import Settings, get_settings
from app.rbac import is_allowed, tool_min_role, user_role
from app.tool_policy import policy_catalog, tool_policy


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


def test_unknown_tool_policy_is_explicit():
    policy = tool_policy("new_runtime_tool_not_in_bff_policy")
    assert policy.known is False
    assert policy.risk == "unknown"
    assert policy.min_role is None


def test_unknown_tool_blocked_by_default():
    assert is_allowed("new_runtime_tool_not_in_bff_policy", "admin", _settings()) is False


def test_unknown_tool_can_be_allowed_when_configured_for_dev():
    s = Settings(mcp_url="http://mock-mcp:8000", block_unknown_tools=False)
    assert is_allowed("new_runtime_tool_not_in_bff_policy", "viewer", s) is True


def test_policy_catalog_groups_known_tools():
    catalog = policy_catalog()
    assert "server_info" in catalog["low"]
    assert "pr_create" in catalog["medium"]
    assert "pr_merge" in catalog["high"]


def test_is_allowed_viewer_can_read():
    assert is_allowed("repo_get", "viewer", _settings()) is True


def test_is_allowed_viewer_blocked_on_write():
    assert is_allowed("pr_create", "viewer", _settings()) is False


def test_is_allowed_operator_can_write():
    assert is_allowed("pr_create", "operator", _settings()) is True


def test_is_allowed_operator_blocked_on_high():
    assert is_allowed("pr_merge", "operator", _settings()) is False


def test_is_allowed_admin_can_do_all_known_tools():
    assert is_allowed("pr_merge", "admin", _settings()) is True
    assert is_allowed("git_update_ref", "admin", _settings()) is True
