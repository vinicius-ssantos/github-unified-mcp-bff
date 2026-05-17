from app.config import Settings

# Explicit high/medium risk tools — default is low
_HIGH_RISK = {
    "pr_merge", "git_update_ref", "pr_dismiss_review",
    "file_apply_unified_diff", "artifact_extract_to_branch",
}
_MEDIUM_RISK = {
    "pr_create", "pr_update", "pr_update_branch", "pr_enable_auto_merge",
    "pr_mark_ready_for_review", "pr_convert_to_draft", "pr_request_reviewers",
    "issue_create", "issue_update", "issue_add_labels", "issue_remove_label",
    "issue_comment", "branch_create", "file_create_or_update", "file_apply_patch",
    "file_patch_commit_prepared", "git_create_blob", "git_create_tree",
    "git_create_commit", "actions_run_workflow",
}

_ROLE_RANK = {"viewer": 0, "operator": 1, "admin": 2}


def tool_min_role(tool_name: str) -> str:
    if tool_name in _HIGH_RISK:
        return "admin"
    if tool_name in _MEDIUM_RISK:
        return "operator"
    return "viewer"


def user_role(username: str, settings: Settings) -> str:
    admins    = {u.strip() for u in settings.rbac_admin_users.split(",")    if u.strip()}
    operators = {u.strip() for u in settings.rbac_operator_users.split(",") if u.strip()}
    if username in admins:
        return "admin"
    if username in operators:
        return "operator"
    return "viewer"


def is_allowed(tool_name: str, role: str) -> bool:
    return _ROLE_RANK.get(role, 0) >= _ROLE_RANK.get(tool_min_role(tool_name), 0)
