# `apps/mcp` — o servidor MCP, como unidade de deploy própria

Serve o endpoint MCP do Foundry Assured sobre **FastMCP 4** ([ADR-027](../../docs/adr/ADR-027-mcp-app-separado-fastmcp-4.md)).

Hoje ele serve **exatamente** o que o `/mcp` do monolito serve: auth de Resource Server do
Entra, autorização por App Role, e a tool `search_docs` com trim de ACL sob a identidade do
chamador. Nenhuma capacidade nova — o critério desta fase é **paridade**.

> **Duas superfícies ao mesmo tempo, de propósito.** O monolito continua servindo `/mcp` até a
> Fase 0c, quando `app/modules/mcpserver/` (e o `fastmcp==3.4.7` que hoje mora no extra
> `agents` do backend) saem de vez.

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
entitlement no modo `shared`), `app.shared.{auth,settings,telemetry}` — e `app.registry`, para
`domain_spec` e `DOMAIN_KINDS`.

O último merece explicação, porque parece atravessar uma fronteira. A ADR-017 proíbe **módulo →
camada de composição**; ela não fala de dois composition roots, porque até agora só havia um.
`mcp_app/main.py` **é** um composition root — o segundo, sobre os mesmos módulos. As alternativas
foram escrever a lista de domínios aqui (a ADR-027 rejeita por nome: duas listas divergem no
primeiro domínio novo, e a divergência não dá erro — só faz as duas superfícies discordarem
sobre o que o usuário pode ver) ou extrair o registry para um módulo próprio (provavelmente o
destino certo, mas refactor estrutural, e esta fase é de paridade). O raciocínio inteiro está no
docstring de `mcp_app/main.py`.

Custou **uma** mudança no monolito: o `from agent_framework_ag_ui import …` do topo de
`app/registry.py` — pacote que vive no extra `agents` — ganhou um `except ModuleNotFoundError`
com um substituto que **falha alto ao ser chamado**. Um backend instalado sem o extra sobe, e o
primeiro domínio que ele tentar montar diz exatamente o que fazer; nada de endpoint que existe
e não responde.

A primeira tentativa foi descer aquele import para dentro das três funções de mount, o que
parecia mais limpo. Não é: dois gates do monolito neutralizam o adapter **trocando o atributo**
`app.registry.add_agent_framework_fastapi_endpoint`, e com o import dentro das funções esse
ponto de troca some — 7 gates ficaram vermelhos antes de a medição apontar isso.

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
```

O CI roda os cinco no job `mcp-app` (`.github/workflows/ci.yml`), que **também** é o gate de
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
