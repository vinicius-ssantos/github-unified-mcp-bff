import os
import tempfile

# Must be set before any app module is imported
_fd, _DB_PATH = tempfile.mkstemp(suffix=".test.db")
os.close(_fd)

os.environ.setdefault("MCP_URL", "http://mock-mcp:8000")
os.environ.setdefault("MCP_TOKEN", "test-token")
os.environ.setdefault("AUDIT_DB_PATH", _DB_PATH)
os.environ.setdefault("JWT_SECRET", "test-secret")
os.environ.setdefault("GITHUB_CLIENT_ID", "")
os.environ.setdefault("GITHUB_CLIENT_SECRET", "")
os.environ.setdefault("RBAC_OPERATOR_USERS", "operator-user")
os.environ.setdefault("RBAC_ADMIN_USERS", "admin-user")
os.environ.setdefault("RBAC_OPERATOR_TEAMS", "myorg/ops")
os.environ.setdefault("RBAC_ADMIN_TEAMS", "myorg/admins")
# High limit so tests never hit it accidentally
os.environ.setdefault("RATE_LIMIT_PER_USER_MAX", "1000")
