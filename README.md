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

## Configuração

Copie `.env.example` para `.env` e preencha:

```bash
cp .env.example .env
```

| Variável | Descrição | Exemplo |
|----------|-----------|---------|
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

O frontend em `http://localhost:5173` já aponta para `http://localhost:8000` por padrão
(`VITE_MCP_URL=http://localhost:8000`).

## Deploy (Render)

O `Dockerfile` está pronto. Configure as variáveis de ambiente no painel do Render:

- `MCP_URL`
- `MCP_TOKEN`
- `ALLOWED_ORIGINS` — inclua o domínio do frontend em produção (ex: `https://seu-app.vercel.app`)

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
