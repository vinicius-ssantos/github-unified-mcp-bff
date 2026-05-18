from app.config import Settings
from app.tool_policy import is_allowed as policy_is_allowed
from app.tool_policy import tool_min_role as policy_tool_min_role


def tool_min_role(tool_name: str) -> str:
    return policy_tool_min_role(tool_name)


def user_role(username: str, settings: Settings, teams: list[str] | None = None) -> str:
    admins = {u.strip() for u in settings.rbac_admin_users.split(",") if u.strip()}
    operators = {u.strip() for u in settings.rbac_operator_users.split(",") if u.strip()}
    admin_teams = {t.strip() for t in settings.rbac_admin_teams.split(",") if t.strip()}
    operator_teams = {t.strip() for t in settings.rbac_operator_teams.split(",") if t.strip()}
    user_teams = set(teams or [])
    if username in admins or bool(user_teams & admin_teams):
        return "admin"
    if username in operators or bool(user_teams & operator_teams):
        return "operator"
    return "viewer"


def is_allowed(tool_name: str, role: str, settings: Settings | None = None) -> bool:
    return policy_is_allowed(tool_name, role, settings)
