# `apps/mcp` — o servidor MCP, como unidade de deploy própria

Serve o endpoint MCP do Foundry Assured sobre **FastMCP 4** ([ADR-027](../../docs/adr/ADR-027-mcp-app-separado-fastmcp-4.md)).

Ele serve auth de Resource Server do Entra, autorização por App Role, e a tool `search_docs`
com trim de ACL sob a identidade do chamador — exatamente o que o `/mcp` do monolito servia,
porque nasceu como porte com critério de **paridade**.

Desde a **Fase 1 (T5)** ele publica mais duas famílias de superfície, e nenhuma das duas declara
conteúdo próprio:

- **prompts** — um por agente do escopo, DERIVADOS dos documentos AgentSchema em
  `apps/backend/agents/assured/` via `app.modules.agentdefs.public.composed_agents()`. Prompt
  literal dentro deste app é PR errado; `tests/prompts_mirror_test.py` é o gate.
- **resource** `document://{domain}/{name}` — o documento integral, reautorizado a cada leitura
  por `app.modules.knowledge.public.authorized_document`, que é a MESMA função da rota
  `GET /source/{domain_id}/{name}` do backend. Mais a **completion** dos dois parâmetros.

E desde a **Fase 2 (T6)**, por cima da tool, o **selo de assurance** — a camada que motivou
a ADR-027 e a única parte deste produto sem equivalente de primeira parte. É uma **extensão de
protocolo negociada** (SEP-2133, `br.com.rededor.foundry/assurance`) que envolve o `tools/call`
e anexa, ao `_meta` da resposta, as citações que a tool produziu e o **id do evento na trilha**
(ADR-023). Duas propriedades a definem, e as duas são de gate:

- **negociada** — quem não anuncia a extensão recebe a resposta de `tools/call` **idêntica** à
  de antes dela. O identificador em si vai para `capabilities.extensions` de TODO cliente que faz
  handshake, negocie ou não (é assim que ele descobre a extensão para poder negociá-la) — só o
  carimbo na resposta de `tools/call` fica condicionado ao opt-in.
- **não calcula nada** — cada campo de conteúdo é cópia de algo que já existia. Um selo que
  recalcula não prova nada, prova a si mesmo.
- **alcance limitado** — `intercept_tool_call` é o único gancho de resposta que a
  `ServerExtension` oferece nesta versão do protocolo: o resource `document://` e a completion
  continuam SEM selo, não por não merecerem, mas porque o protocolo ainda não tem o gancho
  equivalente para eles.

`mcp_app/assurance_extension.py` explica a escolha do identificador (é contrato de fio) e o que
o selo não pode carregar; `tests/assurance_seal_test.py` prova os dois sentidos do opt-in, a
não-invenção por mutação da fonte, e a não-vazão com um chamador sem acesso.

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
  main.py                 composition root: telemetria → empurra o registry → constrói → serve
  auth.py                 AzureJWTVerifier + RemoteAuthProvider, e o gate de App Role
  caller.py               quem perguntou: token do FastMCP → usuário do backend + trilha
  tools_knowledge.py      a tool `search_docs`
  prompts_agentdefs.py    os prompts, derivados dos documentos AgentSchema
  resources_knowledge.py  o documento integral (mesmo ACL da rota /source) + a completion
  assurance_extension.py  o SELO: extensão de protocolo negociada sobre o `tools/call`
tests/                    os gates (módulos executáveis com main(), não pytest)
Dockerfile                contexto de build = a RAIZ do repositório (depende de ../backend por path)
```

`register_surfaces()` em `main.py` é o ÚNICO lugar que lista as superfícies publicadas — e é o
mesmo ponto que o gate de instrumentação monta, para provar o que o app monta e não o que o
teste monta.

**O pacote se chama `mcp_app`, não `app`.** O backend se instala como o pacote `app`; um
diretório `app/` aqui venceria o instalado em `sys.path` e `import app.modules.knowledge.public`
quebraria. `mcp` também está fora — é o SDK do protocolo.

## O que este app importa do monolito

`app.modules.knowledge.public` (a busca, o trim de ACL e a autorização do documento integral),
`app.modules.tenancy.public` (tenant e entitlement no modo `shared`),
`app.modules.audit.public` (a trilha da ADR-023), `app.modules.agentdefs.public` (os prompts
compostos dos documentos AgentSchema), `app.shared.{auth,settings,telemetry}` — e
`app.modules.domains.public`, o **catálogo** de domínios (`DomainSpec`, `DOMAIN_KINDS`,
`domain_spec`, `domain_specs`).

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
uv run python -m tests.instrumentation_matrix_test # toda superfície tem papel e declara o que grava
uv run python -m tests.prompts_mirror_test         # os prompts publicados == os agentes compostos
uv run python -m tests.resource_document_test      # o ACL do documento é o do backend; `..` recusado
uv run python -m tests.completion_test             # só sugere o que existe e o que o chamador pode abrir
uv run python -m tests.client_surface_test         # um cliente REAL atravessa a pilha; sem papel não vê nada
uv run python -m tests.assurance_seal_test         # o selo é negociado, não inventa e não vaza
```

O CI roda todos no job `mcp-app` (`.github/workflows/ci.yml`), que **também** é o gate de
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
