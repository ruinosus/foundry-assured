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

E desde a **Fase 3 (T3)** este servidor **escreve**: a tool `open_ticket`, que é a primeira
superfície MCP a mudar o mundo em vez de descrevê-lo — e a única atrás do contrato de decisão da
[ADR-019](../../docs/adr/ADR-019-langchain-hitl-comparison.md).

- **O transporte é do protocolo, o vocabulário é nosso.** O padrão nativo
  (`InputRequiredResult` + `ElicitResult.action`) é *aceitar-ou-recusar*. O contrato deste
  produto tem **quatro** decisões — aprovar · **editar** · rejeitar · responder — e o `edit` é a
  razão de a ADR existir. As quatro viajam no `enum` do `requested_schema` do
  `ElicitRequestFormParams` e chegam inteiras a `app.modules.hitl.public.decide`, o **mesmo**
  vocabulário que a escalação do helpdesk usa. Nada é reduzido a um booleano.
- **A escrita é inalcançável sem a decisão.** Não há tool de criação separada: `open_ticket` é
  uma *guard tool* que, na primeira rodada, devolve a pergunta. Na segunda ela só segue se
  chegarem juntas a resposta do aprovador **e** o `request_state` que este servidor emitiu —
  selado pelo SDK e amarrado ao principal autenticado, ao nome da tool, ao digest dos argumentos
  e a um TTL. Medido: respostas sem estado recebem a pergunta de novo; estado forjado ou em
  texto puro é recusado no fio, antes de o corpo rodar.
- **O papel é cobrado duas vezes.** `auth=require_any_role("Approver", "Admin")` faz a tool não
  existir para quem não pode decidir; `hitl.decide` recusa de novo lá dentro — e é essa segunda
  que grava a decisão na trilha (ADR-023). Uma escrita aprovada deixa **dois** eventos: a
  decisão e a escrita.
- **Um `requestState`, uma escrita** — e a afirmação é essa, não a versão forte. `mcp_app.decision_claim`
  reserva o NONCE que viaja selado no estado, com `O_CREAT|O_EXCL` no share que já está montado,
  então repetir a mesma chamada com o mesmo estado é recusado (e vira evento `replay` na trilha)
  em vez de abrir um segundo chamado. O que isso **não** prende é o humano: um cliente pode
  chamar `open_ticket` N vezes, receber N estados, mostrar o formulário uma vez e responder as N
  com o mesmo conteúdo — saem N chamados. O protocolo não prova que há alguém do outro lado;
  quem barra é o **papel** do token, que o cliente não escreve.
- **O selo alcança a escrita.** A resposta final é carimbada e carrega os dois eventos da
  trilha; ela não ganha `citations` (esta tool não fundamenta nada — um `[]` mentiria dizendo
  que tentou citar). A rodada da *pergunta* não é carimbada: não é uma resposta.

### Os dois segredos que este app recebe

Nenhum deles mora no repositório (ADR-005): os dois chegam como Container App secret, declarados
em `infra/containerapps.bicep` só quando existem, e os gates geram o seu na hora.

- **`ENTRA_API_CLIENT_SECRET`** — a credencial da app registration da API, que a **leitura** usa.
  `search_docs`, `document://` e a completion chamam o `knowledge.retrieve` do backend, que troca
  o token do chamador por um de busca via **OBO** — fluxo de cliente confidencial. Sem ela,
  `OnBehalfOfCredential` nem constrói (`TypeError: Either "client_certificate", "client_secret",
  or "client_assertion_func" must be provided`) e a tool principal nasce morta no primeiro deploy
  autenticado. Enquanto o `/mcp` morava no monolito o segredo vinha de graça; separado o app, ele
  precisou ser declarado — `tests/obo_credential_test.py` é o gate.
- **`MCP_REQUEST_STATE_KEY`** — a chave que sela a decisão humana da **escrita**, detalhada
  abaixo.

A alternativa sem segredo (`client_assertion_func` sobre a managed identity, via federated
identity credential) é aceita pelo `azure-identity` instalado e **fica pendente de configuração
no Entra**: a FIC precisa confiar numa identidade gerenciada que só existe depois do
`azd provision`, enquanto `scripts/setup-entra.sh` roda antes dele. O comentário do recurso
`mcpApp` no bicep registra a medição e o custo.

### `MCP_REQUEST_STATE_KEY`

A chave (>= 32 bytes) que assina o estado entre as rodadas, **igual em todas as réplicas**. Vem
do ambiente, e no ambiente publicado vem do cofre para a variável — **nunca do repositório**
(ADR-005); os gates geram a sua na hora.

| Estado da variável | O que acontece |
|---|---|
| ausente | o servidor sobe; **só a escrita** se declara indisponível, com erro que diz que é configuração do operador. As quatro superfícies de leitura não mudam. |
| presente, >= 32 bytes | a escrita funciona |
| presente, < 32 bytes | **o app não sobe** — é configuração errada, não um modo |

Derrubar o servidor inteiro por falta de um segredo que só a escrita usa trocaria uma lacuna de
configuração de escrita por indisponibilidade de leitura, sem comprar segurança nenhuma. Deixar
a escrita ligada sobre a chave efêmera do processo (o default do FastMCP) faria a aprovação
falhar de forma intermitente — este app roda com `minReplicas: 0`, isto é, desliga por
ociosidade **entre** a pergunta e a resposta. A justificativa completa está em
`mcp_app/request_state.py`.

Em dev local a regra é a mesma, sem exceção por `auth_enabled`: uma exigência de operação que só
aparece em produção é a que ninguém descobre a tempo.

```bash
python -c "import secrets; print(secrets.token_hex(32))"   # e coloque em MCP_REQUEST_STATE_KEY
```

### O que este servidor deliberadamente NÃO tem (Fase 5, T7)

A camada de escala do FastMCP 4 foi avaliada item a item e **nenhum dos quatro entrou**. As
medições e os gatilhos de reavaliação estão na
[spec](../../docs/superpowers/specs/2026-08-24-mcp-t3-t7-execucao.md#fase-5--t7-escala--os-quatro-itens-recusados-com-medição);
o resumo, porque quem lê este README é quem seria tentado a ligá-los:

| Item | Por que não | Como falharia se alguém ligasse |
|---|---|---|
| **Tasks** (`task=True`) | backend padrão é `memory://` e este app roda com `minReplicas: 0` — medido: processo novo responde `Task not found` depois de prometer `ttl_ms=900000`. E não existe tool lenta aqui | alto: sem o extra, o handshake do servidor inteiro cai |
| **Sessions** (`UserSession`) | store padrão é `MemoryStore()`, de processo. O único estado entre chamadas deste servidor (a decisão humana) já viaja **selado no fio** — melhor que guardado aqui | alto: sem principal autenticado, levanta |
| **Cache** (`cache_ttl`) | `tools/call` não é cacheável, então a busca nunca entra em cache; o hint é uniforme e alcança `resources/read` — o documento com ACL cuja leitura a trilha registra. Um TTL ali vira **buraco na trilha**, não vazamento | **silencioso** — e por isso `tests/cache_hints_test.py` existe |
| **MCP Apps** (`FastMCPApp`) | o prefab `Approval` registra tool com `auth=None` (medido), é binário onde o contrato tem quatro decisões, e devolve o desfecho como mensagem de conversa — sem papel e sem trilha | a matriz de instrumentação fica vermelha |

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
  tools_tickets.py        a ESCRITA `open_ticket`, atrás do contrato de decisão da ADR-019
  request_state.py        a chave que assina o estado entre as rodadas — e o que fazer sem ela
  tenant_gate.py          tenant + entitlement (ADR-010), a MESMA regra do `require_domain`
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

### A porta de CORS foi fechada

Este app **não** tem `CORSMiddleware`, e a ausência é uma decisão, não um esquecimento. Ele
existiu por PARIDADE: no monolito o `/mcp` ficava debaixo do middleware que `app/main.py` aplica
a tudo, e a Fase 0c preservou a permissão em vez de retirá-la em silêncio — dizendo, ali mesmo,
que retirá-la seria decisão separada.

Foi retirada porque a permissão não tem consumidor: o frontend fala **AG-UI com o backend**, não
MCP, e um cliente MCP não roda em browser (o transporte é servidor-a-servidor — sem same-origin
policy, sem preflight). O que sobrava era uma cópia solitária de uma regra que mora no monolito,
e uma permissão de origem cruzada sem consumidor é superfície que ninguém revisa. No fio, um
`OPTIONS` de browser volta a receber 405 sem `access-control-allow-origin`. Se um dia existir um
cliente de browser, o middleware volta como decisão, com o consumidor nomeado.

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
uv run python -m tests.write_decision_test         # as quatro decisões atravessam; sem papel nada escreve
uv run python -m tests.decision_replay_test        # um `requestState`, uma escrita — o estado não se repete
uv run python -m tests.cache_hints_test            # nenhum hint de cache sai daqui (a recusa da Fase 5)
uv run python -m tests.obo_credential_test         # o container recebe a credencial que o OBO exige
uv run lint-imports --config importlinter.toml     # a entrada no backend é pelo `public` (ADR-017)
```

Mais um que **só roda dentro da imagem**, e por isso mora no job `mcp-image` (precisa de
`docker`, que não é offline nem determinístico — ver `scripts/gates.py:42`):

```bash
docker build -f apps/mcp/Dockerfile -t foundry-assured-mcp:ci .     # do repo root
docker run --rm \
  -v "$PWD/infra:/infra:ro" \
  -v "$PWD/apps/mcp/tests/image_data_path_test.py:/gate/image_data_path_test.py:ro" \
  -e MCP_BICEP=/infra/containerapps.bicep -e PYTHONPATH=/gate \
  foundry-assured-mcp:ci python -m image_data_path_test
```

Ele compara o caminho que o código resolve NESTA imagem (`<raiz do backend>/data`, que aqui é
`/srv/backend/data` e não `/app/data` — os Dockerfiles diferem) com o `mountPath` que o bicep
declara para o container do MCP. Sem ele, o chamado aberto por MCP ia para disco efêmero e a
reserva de decisão morria no scale-to-zero, devolvendo o replay que a Fase 3 tinha fechado.

O CI roda todos os demais no job `mcp-app` (`.github/workflows/ci.yml`), que **também** é o gate
de instalabilidade: ele instala a base sem o extra `agents` mais FastMCP 4 e importa
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
