# `apps/mcp` — o servidor MCP, como unidade de deploy própria

Serve o endpoint MCP do Foundry Assured sobre **FastMCP 4** ([ADR-027](../../docs/adr/ADR-027-mcp-app-separado-fastmcp-4.md)).

Ele serve auth de Resource Server do Entra, autorização por App Role, e a tool `search_docs`
com trim de ACL sob a identidade do chamador — exatamente o que o `/mcp` do monolito servia,
porque nasceu como porte com critério de **paridade**.

> **É a ÚNICA superfície MCP do produto.** Na Fase 0c `app/modules/mcpserver/` foi deletado do
> backend, junto com o `fastmcp==3.4.7` do extra `agents` que o sustentava. Duas superfícies
> servindo a mesma tool é a divergência que este projeto mais teme: uma delas pode passar a
> decidir diferente sobre o que o usuário pode ver, sem erro nenhum. A garantia também mudou de
> endereço — os gates em `tests/` aqui são agora o único lugar onde ela é verificada.

## Por que um app separado

O FastMCP 4 exige `mcp>=2,<3`; o `agent-framework` (meta-pacote, isto é
`agent-framework-core[all]`) fixa `mcp>=1.24.0,<2`. Os dois não cabem no mesmo venv. O que
**cabe** é a base do backend **sem** o extra `agents` mais FastMCP 4 — medido, é o que este app
instala. O `agent-framework-declarative` atravessa junto (precisa só do core sem extras), então
os prompts AgentSchema continuam legíveis daqui.

O que torna isso possível não foi planejado: as fronteiras da [ADR-017](../../docs/adr/ADR-017-module-boundaries.md)
produziram, de graça, um núcleo instalável sem framework de agente — `knowledge`, `audit`,
`tenancy` e `shared`. `tests/architecture/nucleo_limpo_test.py`, no backend, é quem prova que
continua assim.

## Layout

```
mcp_app/
  main.py            composition root: telemetria → empurra o registry → constrói → serve
  auth.py            AzureJWTVerifier + RemoteAuthProvider, e o gate de App Role
  tools_knowledge.py a tool `search_docs`
tests/               os gates (módulos executáveis com main(), não pytest)
Dockerfile           contexto de build = a RAIZ do repositório (depende de ../backend por path)
```

**O pacote se chama `mcp_app`, não `app`.** O backend se instala como o pacote `app`; um
diretório `app/` aqui venceria o instalado em `sys.path` e `import app.modules.knowledge.public`
quebraria. `mcp` também está fora — é o SDK do protocolo.

## O que este app importa do monolito

`app.modules.knowledge.public` (a busca e o trim de ACL), `app.modules.tenancy.public` (tenant e
entitlement no modo `shared`), `app.shared.{auth,settings,telemetry}` — e
`app.modules.domains.public`, o **catálogo** de domínios (`DomainSpec`, `DOMAIN_KINDS`,
`domain_spec`).

Tudo isso é `<módulo>.public`, e nada é da camada de composição do monolito. Nem sempre foi
assim: no porte (Fase 0b) o catálogo morava em `apps/backend/app/registry.py`, e este app — que
é um segundo composition root — importava de lá. Funcionava, mas custava um
`try/except ModuleNotFoundError` em volta do `from agent_framework_ag_ui import …` no topo
daquele arquivo, porque o pacote vive no extra `agents` que este app deliberadamente não
instala. A Fase 0c extraiu o catálogo para `app/modules/domains/` (`public.py`/`internal/`,
ADR-017) — ele é dado de negócio, não wiring de FastAPI — e aquele `except` foi embora.

O que **não** mudou: a lista de domínios continua sendo uma só. Escrevê-la aqui é o que a
ADR-027 rejeita por nome — duas listas divergem no primeiro domínio novo, e a divergência não dá
erro; só faz as duas superfícies discordarem sobre o que o usuário pode ver.

## Rodar

```bash
cd apps/mcp
uv sync                                                  # backend por path, SEM o extra `agents`
uv run uvicorn mcp_app.main:app --port 8001 --reload
```

Sem `ENTRA_TENANT_ID`/`ENTRA_API_CLIENT_ID` a auth fica desligada e o servidor responde sem
token — o mesmo degradar-aberto do resto do backend em dev local. Com elas, `POST /mcp/` sem
token devolve **401** com `WWW-Authenticate: Bearer … resource_metadata="…"`, e essa URL
responde 200 com a metadata RFC 9728.

## Gates

```bash
cd apps/mcp
uv run python -m tests.auth_test                   # Resource Server, não authorization server
uv run python -m tests.authz_test                  # papel do Entra decide as tools visíveis
uv run python -m tests.unauthenticated_test        # 401 + a placa que leva a algum lugar
uv run python -m tests.identity_passthrough_test   # o token do CHAMADOR chega ao retrieve
uv run python -m tests.error_masking_test          # erro não conta a infraestrutura
uv run python -m tests.shared_tenancy_test         # no shared, resolve tenant E cobra entitlement
```

O CI roda os seis no job `mcp-app` (`.github/workflows/ci.yml`), que **também** é o gate de
instalabilidade: ele instala a base sem o extra `agents` mais FastMCP 4 e importa
`app.modules.knowledge.public`. O `import-linter` prova o grafo de import; só a instalação prova
a instalabilidade — e é a instalabilidade que quebra.

## Uma nota sobre `require_roles`

O plano era trocar a ponte escrita à mão do monolito (`mcpserver/internal/authz.py`) por
`require_roles(...)` de biblioteca, uma linha. Medido no pacote instalado, o `require_roles` do
FastMCP 4.0.0b3 é **AND** — "All are required (AND logic)". O contrato deste produto é
**any-of** (Reader OU Author OU Approver OU Admin), e a versão AND faria a tool sumir do
`tools/list` para todo mundo, sem erro nenhum, porque uma tool negada por `auth=` é *filtrada*,
não recusada.

`mcp_app.auth.require_any_role` compõe um `require_roles` de biblioteca **por papel** e faz o OR
por cima. Só o OR é nosso; token ausente, claim ausente e claim escalar continuam sendo tratados
pela biblioteca. `tests/authz_test.py` trava as duas semânticas — se um FastMCP futuro trocar
AND por OR, ele fica vermelho e alguém revisita a decisão em vez de herdá-la.
