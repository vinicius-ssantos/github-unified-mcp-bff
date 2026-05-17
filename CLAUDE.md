# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Priority Order

Follow this order for all work:

1. Never expose `MCP_TOKEN` to the browser — it must stay server-side
2. CORS and origin validation before any new endpoint
3. Small, explicit, testable changes
4. Test coverage for proxy behavior and error paths
5. Documentation updated when architecture or env vars change

## Project Purpose

FastAPI BFF (Backend for Frontend) that sits between the React operator console
(`github-unified-mcp-frontend`) and the MCP server (`github-unified-mcp`):

```
Browser (no token)
  → github-unified-mcp-bff  ← auth, CORS, RBAC (future), audit (future)
      → github-unified-mcp  ← MCP_TOKEN stays here, server-side
          → GitHub API
```

Current scope: Camada 1 — transparent proxy. The bearer token for the MCP server
is never sent to the browser.

**Stack:** Python 3.11+, FastAPI, httpx, uvicorn, pydantic-settings, pytest, respx

## Commands

```powershell
# Install (first time — inside .venv)
pip install -e ".[dev]"

# Run local server (requires .env)
python main.py

# Run tests
pytest -q

# Run a single test file
pytest tests/test_proxy.py -q
```

## Architecture

```
app/
  config.py   — Settings from env vars (MCP_URL, MCP_TOKEN, ALLOWED_ORIGINS, PORT)
  proxy.py    — POST /api/mcp/call → forwards JSON-RPC to MCP server
  main.py     — FastAPI app, CORS middleware, healthz endpoint
main.py       — uvicorn dev entrypoint
tests/
  test_proxy.py — proxy behavior, error mapping, validation
```

### Key Relationships

`app/config.py` loads all env vars via pydantic-settings. `app/proxy.py` uses
`Depends(get_settings)` to inject them — never read env vars directly in endpoint
code. `app/main.py` initializes CORS from `settings.allowed_origins` at startup.

## Security Rules

- `MCP_TOKEN` is loaded from env and injected into `Authorization: Bearer` headers
  sent **to the MCP server**; it must never appear in any response body or log
- `ALLOWED_ORIGINS` must be explicitly configured — do not use `allow_origins=["*"]`
  in production
- Never add endpoints that return the value of `MCP_TOKEN` or any secret
- All writes to the MCP server go through `POST /api/mcp/call` only — no other
  outbound endpoints without review

## Implementation Conventions

- New endpoints must use `Depends(get_settings)` — no direct `os.environ` calls
- HTTP errors from the MCP server are mapped to matching HTTP status codes
- Timeouts return 504, connection errors return 502
- Request validation errors (422) come automatically from FastAPI/pydantic
- Keep endpoint handlers thin — extract logic to helper functions if it grows

## Tests and Quality

Every non-trivial change must include or update tests:

- Use `respx.mock` to intercept httpx calls — no real network in tests
- Test success path, MCP error (4xx/5xx), timeout (504), unreachable (502)
- Test input validation (missing required fields → 422)
- Before finishing, run: `pytest -q`

Test files live in `tests/`. Env vars required by the app must be set via
`os.environ.setdefault` before importing `app.main` in test files.

## Git Workflow

- Never implement new features directly on `main`
- Use topic branches: `feat/*`, `fix/*`, `docs/*`
- Prefer small, coherent commits
- Never revert user changes without explicit request

## Roadmap Layers

| Layer | Scope | Status |
|-------|-------|--------|
| Camada 1 | Transparent proxy — MCP_TOKEN server-side | current |
| Camada 2 | GitHub OAuth login + JWT session + RBAC roles | planned |
| Camada 3 | Persistent audit log + destructive ops enabled | planned |

## Projects V2 Operational Source of Truth

- Use organization-owned Project V2 as the operational source of truth:
  - Org: `vinicius-automation`
  - Project number: `1`
  - URL: `https://github.com/orgs/vinicius-automation/projects/1`
- Before starting significant work, and again before finalizing, consult Project V2
  state to keep execution aligned with active priorities.
- Keep active repository issues mapped to the org project whenever relevant and
  classify them with `Workflow`, `Track`, `Priority`, `Risk`, and `Effort`.

## Projects V2 Operational Hygiene

- Mandatory flow per task:
  - Before work: review active items and priorities in Project V2.
  - During work: update item status when state changes (`Backlog`, `Ready`, `In Progress`, `Review`, `Done`).
  - After work: sync outcome and classification fields.
- Treat outdated project data as an operational bug and correct it in the same
  execution cycle whenever possible.
