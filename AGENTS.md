# AGENTS.md

## Prioridade

Siga esta ordem em todo trabalho:

1. nunca expor `MCP_TOKEN` ao browser — ele deve ficar server-side
2. CORS e validação de origin antes de qualquer novo endpoint
3. mudanças pequenas, explícitas e testáveis
4. cobertura de testes para comportamento do proxy e caminhos de erro
5. documentação atualizada quando arquitetura ou variáveis de ambiente mudarem

## Objetivo do Repositório

BFF (Backend for Frontend) FastAPI que fica entre o console React
(`github-unified-mcp-frontend`) e o servidor MCP (`github-unified-mcp`):

```
Browser (sem token)
  → github-unified-mcp-bff  ← auth, CORS, RBAC (futuro), audit (futuro)
      → github-unified-mcp  ← MCP_TOKEN fica aqui, server-side
          → GitHub API
```

Escopo atual: Camada 1 — proxy transparente. O bearer token do MCP nunca chega ao browser.

## Regras de Segurança

- `MCP_TOKEN` é carregado de env e injetado no header `Authorization: Bearer` enviado
  **ao servidor MCP**; jamais deve aparecer em resposta ou log
- `ALLOWED_ORIGINS` deve ser configurado explicitamente — não usar `allow_origins=["*"]` em produção
- nenhum endpoint pode retornar o valor de `MCP_TOKEN` ou qualquer secret
- todas as chamadas ao MCP saem por `POST /api/mcp/call` — nenhum outro outbound sem revisão

## Convenções de Implementação

- novos endpoints devem usar `Depends(get_settings)` — sem leitura direta de `os.environ`
- erros HTTP do MCP são mapeados para o mesmo código HTTP na resposta ao cliente
- timeout → 504, connection error → 502
- erros de validação (422) são automáticos via FastAPI/pydantic
- manter handlers finos; extrair lógica para funções auxiliares se crescer

## Testes e Qualidade

Toda mudança não trivial deve incluir ou atualizar testes:

- usar `respx.mock` para interceptar chamadas httpx — sem rede real nos testes
- testar: sucesso, erro MCP (4xx/5xx), timeout (504), inacessível (502), campo faltando (422)
- antes de concluir, rodar: `pytest -q`

Variáveis de ambiente obrigatórias devem ser definidas via `os.environ.setdefault`
antes de importar `app.main` nos arquivos de teste.

## Git e Fluxo de Trabalho

- não implementar feature nova diretamente em `main`
- usar branch temática: `feat/*`, `fix/*`, `docs/*`
- preferir commits pequenos e coerentes
- não reverter alterações do usuário sem pedido explícito

## Roadmap de Camadas

| Camada | Escopo | Estado |
|--------|--------|--------|
| Camada 1 | Proxy transparente — MCP_TOKEN server-side | atual |
| Camada 2 | Login GitHub OAuth + sessão JWT + roles RBAC | planejado |
| Camada 3 | Audit log persistido + ops destrutivas habilitadas | planejado |

## Projects V2 como Fonte Operacional

- usar como fonte operacional o Project V2 organizacional:
  - org: `vinicius-automation`
  - project_number: `1`
  - url: `https://github.com/orgs/vinicius-automation/projects/1`
- antes de iniciar trabalho relevante e antes de concluir, consultar o estado do
  Project para alinhar execução com prioridades ativas.
- espelhar issues ativas do repositório no Project da org quando fizer sentido e
  classificar com `Workflow`, `Track`, `Priority`, `Risk` e `Effort`.

## Higiene Operacional de Projects V2

- fluxo obrigatório por tarefa:
  - antes de trabalhar: revisar itens ativos e prioridades no Project V2;
  - durante o trabalho: atualizar estado quando houver mudança (`Backlog`, `Ready`, `In Progress`, `Review`, `Done`);
  - após concluir: sincronizar campos de classificação e resultado.
- tratar dado desatualizado no Project como bug operacional e corrigir no mesmo ciclo.
