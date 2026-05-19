# github-unified-mcp-bff

BFF (Backend for Frontend) FastAPI entre o console React e o servidor MCP.

## Por que existe

O console `github-unified-mcp-frontend` precisa chamar o `github-unified-mcp` sem expor o bearer token no browser. Este serviço fica no meio:

```text
Browser (sem token)
  → github-unified-mcp-bff   ← adiciona auth server-side, sessão, RBAC, CSRF, audit e policy
      → github-unified-mcp   ← MCP_TOKEN nunca chega ao browser
          → GitHub API
```

## Endpoints

| Método | Path | Descrição |
|--------|------|-----------|
| `GET` | `/healthz` | Proxeia o `/healthz` do MCP server |
| `POST` | `/mcp` | Passthrough raw JSON-RPC; aplica policy quando `method=tools/call` |
| `POST` | `/api/mcp/call` | Chamada estruturada `{ name, arguments }` → JSON-RPC MCP |
| `GET` | `/api/capabilities` | Contrato estável da UI: sessão, role, auth mode, features e limites |
| `GET` | `/auth/login` | Inicia login GitHub OAuth |
| `GET` | `/auth/callback` | Callback OAuth; cria cookies e redireciona para `FRONTEND_URL` |
| `GET` | `/auth/me` | Retorna usuário/role autenticado |
| `POST` | `/auth/logout` | Remove cookies de sessão/CSRF |
| `GET` | `/api/audit` | Lista audit events; proteção por role ainda pendente |

## Configuração

Copie `.env.example` para `.env` e preencha:

```bash
cp .env.example .env
```

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `BFF_ENV` | Ambiente do BFF (`development`, `staging`, `production`) | `development` |
| `FRONTEND_URL` | URL para retorno pós-login OAuth | `http://localhost:5173` |
| `COOKIE_SECURE` | Define cookies com atributo `Secure` | `false` em dev, `true` em produção |
| `COOKIE_SAMESITE` | Política SameSite dos cookies | `lax`, `none`, `strict` |
| `COOKIE_DOMAIN` | Domínio opcional dos cookies | vazio ou `.example.com` |
| `MCP_URL` | URL do servidor MCP | `https://github-unified-mcp.onrender.com` |
| `MCP_TOKEN` | Bearer token estático do MCP | definido apenas server-side |
| `MCP_OAUTH_AUTHORIZATION_SECRET` | Alternativa OAuth service-account BFF → MCP | vazio ou secret server-side |
| `ALLOWED_ORIGINS` | Origins CORS permitidas, separadas por vírgula | `http://localhost:5173` |
| `PORT` | Porta local | `8000` |
| `GITHUB_CLIENT_ID` | Client ID do GitHub OAuth | app OAuth do GitHub |
| `GITHUB_CLIENT_SECRET` | Client secret do GitHub OAuth | secret server-side |
| `GITHUB_CALLBACK_URL` | Callback OAuth cadastrado no GitHub | `http://localhost:8000/auth/callback` |
| `JWT_SECRET` | Secret para assinar sessão JWT | trocar em produção |
| `JWT_TTL_SECONDS` | TTL da sessão | `3600` |
| `RBAC_OPERATOR_USERS` | Usuários GitHub com role operator | `user1,user2` |
| `RBAC_ADMIN_USERS` | Usuários GitHub com role admin | `admin1` |
| `RBAC_OPERATOR_TEAMS` | Times GitHub operator | `org/ops` |
| `RBAC_ADMIN_TEAMS` | Times GitHub admin | `org/admins` |
| `RATE_LIMIT_PER_USER_MAX` | Máximo de requests por janela | `60` |
| `RATE_LIMIT_PER_USER_WINDOW` | Janela do rate limit em segundos | `60` |
| `BLOCK_UNKNOWN_TOOLS` | Bloqueia tools ausentes da policy do BFF | `true` |
| `AUDIT_DB_PATH` | Caminho SQLite do audit log | `audit.db` |
| `AUDIT_RETENTION_DAYS` | Retenção dos eventos de audit | `90` |

## Desenvolvimento

```bash
# Instalar dependências
pip install -e ".[dev]"

# Rodar servidor local
python main.py

# Rodar testes
pytest -q

# Rodar lint
ruff check .
```

O servidor sobe em `http://localhost:8000`.

## Stack local completo

```bash
# Terminal 1 — BFF
cd github-unified-mcp-bff
python main.py

# Terminal 2 — Console
cd github-unified-mcp-frontend
npm run dev
```

O frontend em `http://localhost:5173` deve apontar para o BFF, não diretamente para o MCP core, em modo produção.

## Contrato `/api/capabilities`

O frontend deve consultar `GET /api/capabilities` para descobrir sessão, role, modo de autenticação e recursos habilitados sem inferir comportamento por tentativa/erro.

Exemplo de payload:

```json
{
  "service": "github-unified-mcp-bff",
  "version": "0.2.0",
  "environment": "production",
  "authenticated": true,
  "user": {
    "login": "vinicius-ssantos",
    "name": "Vinicius Santos",
    "role": "admin"
  },
  "auth": {
    "github_oauth_configured": true,
    "csrf_required": true,
    "cookie_session": true,
    "frontend_url_configured": true,
    "cookie_samesite": "none",
    "cookie_secure": true
  },
  "mcp": {
    "auth_mode": "static_bearer",
    "raw_passthrough_enabled": true,
    "structured_call_enabled": true
  },
  "features": {
    "audit": true,
    "audit_protected": false,
    "controlled_operations": false,
    "tool_policy": true,
    "unknown_tools_blocked": true
  },
  "limits": {
    "rate_limit_per_user_max": 60,
    "rate_limit_per_user_window": 60
  }
}
```

O payload não deve expor tokens, secrets, cookies ou headers sensíveis.

## Frontend Vercel → BFF Render

Para frontend e BFF em origens diferentes, use cookies cross-site seguros:

```bash
BFF_ENV=production
FRONTEND_URL=https://seu-app.vercel.app
ALLOWED_ORIGINS=https://seu-app.vercel.app
COOKIE_SECURE=true
COOKIE_SAMESITE=none
```

O callback OAuth do GitHub redireciona para `FRONTEND_URL` depois de criar os cookies de sessão. O cookie `bff_session` é `HttpOnly`; o cookie `csrf_token` fica legível pelo frontend para envio em `X-CSRF-Token`.

## Tool policy

O BFF mantém uma policy explícita de tools em `app/tool_policy.py`.

- Tools low-risk exigem `viewer`.
- Tools medium-risk exigem `operator`.
- Tools high-risk exigem `admin`.
- Tools desconhecidas são bloqueadas por padrão via `BLOCK_UNKNOWN_TOOLS=true`.

A mesma policy é aplicada em:

- `POST /api/mcp/call`;
- `POST /mcp` quando o payload JSON-RPC usa `method="tools/call"`.

Métodos raw que não são `tools/call`, como `tools/list`, continuam compatíveis com passthrough.

## Deploy (Render)

O `Dockerfile` está pronto. Configure as variáveis de ambiente no painel do Render:

- `BFF_ENV=production`
- `FRONTEND_URL=https://<frontend>.vercel.app`
- `COOKIE_SECURE=true`
- `COOKIE_SAMESITE=none` quando frontend e BFF estiverem em domínios diferentes
- `MCP_URL` usando `https://` e sem apontar para localhost/rede privada
- `MCP_TOKEN` ou `MCP_OAUTH_AUTHORIZATION_SECRET`
- `JWT_SECRET` forte, diferente de `change-me-in-production`
- `ALLOWED_ORIGINS` explícito, sem `*`
- `BLOCK_UNKNOWN_TOOLS=true`

Em `BFF_ENV=production`, o BFF falha no startup se a configuração estiver insegura.

## Audit log

O audit atual usa SQLite via `AUDIT_BACKEND=sqlite`, com caminho em `AUDIT_DB_PATH` e retenção controlada por `AUDIT_RETENTION_DAYS`. O BFF não persiste argumentos brutos, apenas hash dos argumentos.

O endpoint `GET /api/audit/health` retorna diagnóstico seguro do storage de audit:

```json
{
  "ok": true,
  "backend": "sqlite",
  "sqlite_persistence": "persistent",
  "path": "/var/data/audit.db",
  "schema_version": "1",
  "events_total": 42,
  "retention_days": 90
}
```

Para desenvolvimento local, `AUDIT_SQLITE_PERSISTENCE=ephemeral` e `AUDIT_DB_PATH=audit.db` são suficientes. Em produção, use disco persistente no Render e configure:

```bash
AUDIT_BACKEND=sqlite
AUDIT_SQLITE_PERSISTENCE=persistent
AUDIT_DB_PATH=/var/data/audit.db
AUDIT_RETENTION_DAYS=90
```

Em `BFF_ENV=production`, o BFF falha no startup se `AUDIT_SQLITE_PERSISTENCE` não for `persistent`, se o caminho apontar para storage efêmero conhecido como `audit.db`, `:memory:` ou `/tmp/...`, ou se `AUDIT_DB_PATH` não for absoluto.

Postgres ainda não foi implementado; `AUDIT_BACKEND=sqlite` é o único backend aceito neste momento.

## Roadmap

| Camada | Escopo | Estado |
|--------|--------|--------|
| Camada 1 | Proxy transparente — `MCP_TOKEN` server-side | ✅ atual |
| Camada 2 | Login GitHub OAuth + sessão JWT + roles RBAC | parcial |
| Camada 3 | Audit log persistido + operações destrutivas controladas | planejado |

## Segurança

- `MCP_TOKEN` nunca aparece em resposta, log ou header de saída.
- `ALLOWED_ORIGINS` deve ser explícito — sem `*` em produção.
- `bff_session` é `HttpOnly`.
- `csrf_token` é legível pelo frontend para envio em `X-CSRF-Token`.
- Tools desconhecidas são bloqueadas por padrão.
- Nenhum endpoint deve retornar o valor de secrets ou tokens.
