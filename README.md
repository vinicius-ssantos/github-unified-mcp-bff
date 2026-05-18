# github-unified-mcp-bff

BFF (Backend for Frontend) FastAPI entre o console React e o servidor MCP.

## Por que existe

O console `github-unified-mcp-frontend` precisa chamar o `github-unified-mcp` sem
expor o bearer token no browser. Este serviço fica no meio:

```
Browser (sem token)
  → github-unified-mcp-bff   ← adiciona auth server-side
      → github-unified-mcp   ← MCP_TOKEN nunca chega ao browser
          → GitHub API
```

## Endpoints

| Método | Path | Descrição |
|--------|------|-----------|
| `GET` | `/healthz` | Proxeia o `/healthz` do MCP server (version, uptime, commit_sha) |
| `POST` | `/mcp` | Passthrough raw JSON-RPC — adiciona `Authorization: Bearer` |
| `POST` | `/api/mcp/call` | Chamada estruturada `{ name, arguments }` → JSON-RPC |
| `GET` | `/api/capabilities` | Contrato estável para UI: sessão, role, auth mode, features e limites |

## Configuração

Copie `.env.example` para `.env` e preencha:

```bash
cp .env.example .env
```

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
| `BFF_ENV` | Ambiente do BFF (`development`, `staging`, `production`) | `development` |
| `MCP_URL` | URL do servidor MCP | `https://github-unified-mcp.onrender.com` |
| `MCP_TOKEN` | Bearer token do MCP | `3nFF8s25h2W1...` |
| `ALLOWED_ORIGINS` | Origins CORS permitidas (vírgula) | `http://localhost:5173` |
| `PORT` | Porta local | `8000` |

## Desenvolvimento

```bash
# Instalar dependências (primeira vez)
pip install -e ".[dev]"

# Rodar servidor local
python main.py

# Rodar testes
pytest -q

# Rodar lint
ruff check .
```

O servidor sobe em `http://localhost:8000`.

## Contrato de capacidades da UI

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
    "tool_policy": false
  },
  "limits": {
    "rate_limit_per_user_max": 60,
    "rate_limit_per_user_window": 60
  }
}
```

O payload nunca deve expor tokens, secrets, cookies ou headers sensíveis.

## Stack local completo

```bash
# Terminal 1 — BFF
cd github-unified-mcp-bff
python main.py

# Terminal 2 — Console
cd github-unified-mcp-frontend
npm run dev
```

O frontend em `http://localhost:5173` já aponta para `http://localhost:8000` por padrão
(`VITE_MCP_URL=http://localhost:8000`).

## Deploy (Render)

O `Dockerfile` está pronto. Configure as variáveis de ambiente no painel do Render:

- `BFF_ENV=production`
- `FRONTEND_URL` — URL pública do frontend para retorno pós-login (ex: `https://seu-app.vercel.app`)
- `COOKIE_SECURE=true`
- `COOKIE_SAMESITE=none` para frontend e BFF em domínios diferentes (ex: Vercel → Render)
- `COOKIE_DOMAIN` — opcional; deixe vazio salvo se houver domínio compartilhado controlado
- `MCP_URL` — deve usar `https://` e não apontar para localhost/rede privada
- `MCP_TOKEN` ou `MCP_OAUTH_AUTHORIZATION_SECRET`
- `JWT_SECRET` — valor forte, diferente de `change-me-in-production`
- `ALLOWED_ORIGINS` — inclua o domínio do frontend em produção (ex: `https://seu-app.vercel.app`) e não use `*`

Em `BFF_ENV=production`, o BFF falha no startup se a configuração estiver insegura.

### Frontend Vercel → BFF Render

Para frontend e BFF em origens diferentes, use cookies cross-site seguros:

```bash
BFF_ENV=production
FRONTEND_URL=https://seu-app.vercel.app
ALLOWED_ORIGINS=https://seu-app.vercel.app
COOKIE_SECURE=true
COOKIE_SAMESITE=none
```

O callback OAuth do GitHub redireciona para `FRONTEND_URL` depois de criar os cookies de sessão.
O cookie `bff_session` é `HttpOnly`; o cookie `csrf_token` fica legível pelo frontend para envio em `X-CSRF-Token`.

## Roadmap

| Camada | Escopo | Estado |
|--------|--------|--------|
| Camada 1 | Proxy transparente — `MCP_TOKEN` server-side | ✅ atual |
| Camada 2 | Login GitHub OAuth + sessão JWT + roles RBAC | planejado |
| Camada 3 | Audit log persistido + operações destrutivas habilitadas | planejado |

## Segurança

- `MCP_TOKEN` nunca aparece em resposta, log ou header de saída
- `ALLOWED_ORIGINS` deve ser explícito — sem `*` em produção
- Nenhum endpoint retorna o valor de secrets ou tokens
