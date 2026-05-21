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
| `GET` | `/api/audit` | Lista audit events; exige sessão e role `operator` ou `admin` |

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
# Instalar dependências com lockfile de desenvolvimento
pip install -e ".[dev]" --constraint requirements-dev.lock

# Rodar servidor local
python main.py

# Rodar testes
pytest -q

# Rodar lint
ruff check .
```

O servidor sobe em `http://localhost:8000`.

## Dependências reproduzíveis

A estratégia de lockfile usa constraints do `pip`:

- `requirements.lock` fixa dependências de produção;
- `requirements-dev.lock` fixa dependências de produção, teste e lint;
- CI instala `.[dev]` usando `--constraint requirements-dev.lock`;
- Docker instala o pacote usando `--constraint requirements.lock`.

Comandos recomendados:

```bash
# Instalação local de desenvolvimento
pip install -e ".[dev]" --constraint requirements-dev.lock

# Instalação de produção equivalente ao Dockerfile
pip install . --constraint requirements.lock

# Validação antes de abrir PR
pytest -q
ruff check .
docker build -t github-unified-mcp-bff:test .
```

Para atualizar dependências, faça preferencialmente em PR separado: atualize as versões nos lockfiles, rode testes completos, rode lint e valide o Docker build. Pacotes críticos de segurança como `fastapi`, `httpx`, `python-jose[cryptography]`, `pydantic-settings` e `aiosqlite` devem permanecer fixados nos lockfiles.

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
    "raw_passthrough_enabled": false,
    "raw_tool_execution_enabled": false,
    "structured_call_enabled": true
  },
  "features": {
    "audit": true,
    "audit_protected": true,
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

## Operações controladas — preview inicial

O BFF expõe o primeiro slice do fluxo de operações controladas com preview server-side, sem executar a tool no MCP:

```http
POST /api/operations/preview
```

Payload:

```json
{
  "tool_name": "issue_create",
  "arguments": {
    "title": "Título seguro",
    "body": "Descrição"
  }
}
```

Resposta segura:

```json
{
  "operation_id": "op_...",
  "tool_name": "issue_create",
  "arguments_hash": "...",
  "arguments_redacted": {
    "title": "Título seguro",
    "body": "Descrição"
  },
  "requested_by": "vinicius-ssantos",
  "role": "operator",
  "risk_level": "medium",
  "min_role": "operator",
  "status": "previewed",
  "created_at": "2026-05-20T00:00:00+00:00",
  "expires_at": "2026-05-20T00:05:00+00:00"
}
```

O preview exige sessão autenticada, usa a mesma policy de tools/RBAC do BFF, redige chaves sensíveis nos argumentos e expira operações pendentes em memória. A primeira versão é intencionalmente preview-only: confirmação, execução MCP e audit de ciclo completo entram em slices posteriores da #7.

Também é possível consultar o preview pendente por `GET /api/operations/{operation_id}`. Apenas o usuário que criou a operação ou um admin pode ler o preview.

## Contrato de erro para o frontend

`POST /api/mcp/call` preserva o campo legado `detail` e também retorna um envelope estável em `error` quando uma chamada falha:

```json
{
  "detail": "MCP server timeout",
  "error": {
    "code": "mcp_timeout",
    "message": "MCP server timeout",
    "details": {
      "status_code": 504
    }
  }
}
```

Códigos esperados para UI:

| HTTP | `error.code` | Uso recomendado |
|------|--------------|-----------------|
| `401` | `unauthorized` | Pedir login novamente |
| `403` | `forbidden` | Mostrar falta de permissão ou CSRF inválido |
| `429` | `rate_limited` | Mostrar retry/backoff |
| `502` | `mcp_unreachable` | Mostrar indisponibilidade do MCP |
| `504` | `mcp_timeout` | Mostrar timeout e permitir tentar novamente |
| `5xx` do MCP | `mcp_server_error` | Mostrar falha segura sem detalhes sensíveis |

O BFF não repassa tokens, headers ou payload sensível em erros retornados ao browser.

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

Em desenvolvimento, o passthrough raw pode continuar habilitado para compatibilidade/debug. Em produção, a configuração segura desabilita o endpoint raw e também a execução de tools pelo caminho raw; o frontend deve usar `POST /api/mcp/call`.

Métodos raw que não são `tools/call`, como `tools/list`, continuam compatíveis com passthrough apenas quando a política raw estiver habilitada.

## Operações controladas

O primeiro slice do fluxo de operações controladas é preview-only. Ele permite que o frontend peça ao BFF uma prévia segura antes de qualquer execução de tool sensível.

Endpoints disponíveis:

- `POST /api/operations/preview` cria uma operação pendente com status `previewed`;
- `GET /api/operations/{operation_id}` consulta uma operação pendente existente.

O preview exige sessão autenticada e aplica a mesma policy local de tools:

- medium-risk exige `operator`;
- high-risk exige `admin`;
- tools desconhecidas continuam bloqueadas por padrão.

A resposta inclui `operation_id`, `tool_name`, `arguments_hash`, `arguments_redacted`, `requested_by`, `role`, `risk_level`, `min_role`, `status`, `created_at` e `expires_at`. Argumentos sensíveis com nomes contendo `token`, `secret`, `password`, `authorization` ou `code` são redigidos no preview.

Este slice ainda não executa operações. `POST /api/operations/preview` não chama o MCP core, não escreve no GitHub e não confirma ações destrutivas. A confirmação, execução server-side e audit completo do ciclo de vida devem entrar em slices posteriores da #7.

`GET /api/capabilities` expõe `features.operation_preview=true` e `features.operation_execution=false` para o frontend diferenciar preview disponível de execução ainda indisponível.

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
- desabilite passthrough raw do MCP em produção
- desabilite execução de tools pelo caminho raw em produção

Em `BFF_ENV=production`, o BFF falha no startup se a configuração estiver insegura.

## Audit log

O audit atual usa SQLite via `AUDIT_BACKEND=sqlite`, com caminho em `AUDIT_DB_PATH` e retenção controlada por `AUDIT_RETENTION_DAYS`. O BFF não persiste argumentos brutos, apenas hash dos argumentos.

A leitura de audit é protegida por sessão e RBAC:

- `GET /api/audit` sem sessão retorna `401`.
- Usuário autenticado com role `viewer` recebe `403`.
- Roles `operator` e `admin` podem consultar eventos de audit.
- `GET /api/audit/health` usa a mesma política, porque expõe metadados operacionais do storage.

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
