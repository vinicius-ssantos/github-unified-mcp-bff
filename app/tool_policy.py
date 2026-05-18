from dataclasses import dataclass
from typing import Literal

from app.config import Settings

RiskLevel = Literal["low", "medium", "high", "unknown"]
Role = Literal["viewer", "operator", "admin"]

_ROLE_RANK: dict[str, int] = {"viewer": 0, "operator": 1, "admin": 2}

_LOW_RISK_TOOLS = {
    "server_info",
    "repo_get",
    "repo_tree",
    "repo_context_atlas",
    "repo_search_code",
    "file_get_range",
    "issue_list",
    "issue_get",
    "pr_list",
    "pr_get",
    "pr_diff",
    "pr_files",
    "pr_comments",
    "pr_reviews",
    "pr_ready_to_merge",
    "pr_risk_review",
    "actions_list_runs",
    "actions_get_run",
    "actions_get_jobs",
    "actions_get_job_logs",
    "actions_list_artifacts",
    "compare_commits",
    "dependency_scan",
}

_MEDIUM_RISK_TOOLS = {
    "pr_create",
    "pr_update",
    "pr_update_branch",
    "pr_enable_auto_merge",
    "pr_mark_ready_for_review",
    "pr_convert_to_draft",
    "pr_request_reviewers",
    "issue_create",
    "issue_update",
    "issue_add_labels",
    "issue_remove_label",
    "issue_comment",
    "branch_create",
    "file_create_or_update",
    "file_apply_patch",
    "file_patch_preview",
    "file_patch_commit_prepared",
    "git_create_blob",
    "git_create_tree",
    "git_create_commit",
    "actions_run_workflow",
}

_HIGH_RISK_TOOLS = {
    "pr_merge",
    "git_update_ref",
    "pr_dismiss_review",
    "file_apply_unified_diff",
    "artifact_extract_to_branch",
}


@dataclass(frozen=True)
class ToolPolicy:
    name: str
    risk: RiskLevel
    min_role: Role | None
    known: bool


def tool_policy(tool_name: str) -> ToolPolicy:
    if tool_name in _HIGH_RISK_TOOLS:
        return ToolPolicy(name=tool_name, risk="high", min_role="admin", known=True)
    if tool_name in _MEDIUM_RISK_TOOLS:
        return ToolPolicy(name=tool_name, risk="medium", min_role="operator", known=True)
    if tool_name in _LOW_RISK_TOOLS:
        return ToolPolicy(name=tool_name, risk="low", min_role="viewer", known=True)
    return ToolPolicy(name=tool_name, risk="unknown", min_role=None, known=False)


def tool_min_role(tool_name: str) -> Role:
    policy = tool_policy(tool_name)
    return policy.min_role or "admin"


def is_allowed(tool_name: str, role: str, settings: Settings | None = None) -> bool:
    policy = tool_policy(tool_name)
    if not policy.known:
        if settings is None:
            return False
        return not settings.block_unknown_tools
    return _ROLE_RANK.get(role, 0) >= _ROLE_RANK[policy.min_role or "admin"]


def policy_catalog() -> dict[str, list[str]]:
    return {
        "low": sorted(_LOW_RISK_TOOLS),
        "medium": sorted(_MEDIUM_RISK_TOOLS),
        "high": sorted(_HIGH_RISK_TOOLS),
    }
