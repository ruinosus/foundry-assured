---
title: 'Execução: T3–T7 do MCP sobre o app separado (FastMCP 4)'
description: Do endpoint com uma tool de leitura ao produto — prompts e resources derivados da fonte única, o selo de assurance como extensão de protocolo negociada, escrita atrás do contrato de decisão de quatro opções, OBO nativo, e a camada de escala. Cada API citada foi lida do pacote 4.0.0b3 instalado, não da documentação.
type: design
audience: contributor
status: draft
updated: 2026-08-25
---

# T3–T7: do endpoint ao produto

## O que já existe, e o que falta

Na `main` (PR #203): `/mcp` dentro do monolito, sobre `fastmcp==3.4.7`, com auth de Resource Server
do Entra, autorização por App Role, e **uma tool de leitura** (`search_docs`, com trim de ACL por
documento). Zero resources, zero prompts, zero extensões.

Na branch `release/mcp-t3-t7`: o **núcleo limpo** — `knowledge`, `audit`, `tenancy`, `tickets`,
`hitl` e `shared` sem framework de agente, com gate duplo (contrato estático + teste de import
transitivo em subprocesso).

Esta spec cobre o resto: **T3 a T7**, sobre o app separado da ADR-027.

## As APIs, medidas — não lidas da documentação

`fastmcp==4.0.0b3` instalado num venv descartável e inspecionado (regra 1). Resolve com
`mcp 2.1.0`, `httpx2 2.12.0`, `starlette 1.6.0`, `pydantic 2.14.0b1`.

| Peça | Assinatura real |
|---|---|
| `ServerExtension` | `identifier` (**sem default** — obrigatório), `settings() -> dict`, `methods() -> Sequence[MethodBinding]`, `intercept_tool_call(params, context, call_next) -> ToolCallOutcome`, `lifespan()`, `client_settings`, `server` |
| `require_roles` | `(*roles: str, extract: Callable[[dict], Iterable[str]]) -> AuthCheck` — `extract` é **obrigatório**; e a semântica é **AND**, não OR (medido na Fase 0b) |
| `EntraOBOToken` | `(scopes: list[str]) -> str` |
| `AzureJWTVerifier` | `(*, client_id, tenant_id, required_scopes=None, identifier_uri=None, base_authority='login.microsoftonline.com')` — **idêntica à do 3.4.7** |
| `UserSession` | `get` · `set` · `delete` · `clear` · `end` · `id` |
| `FastMCP()` | ganha `resource_security`, `request_state_security`, `cache_ttl`, `cache_scope`, `tasks`, `session_state_store` |
| HITL nativo | `InputRequiredResult`, `InputRequest(s)`, `InputResponse(s)`, `ElicitRequest`, `ElicitRequestFormParams` — todos em `mcp.types` |
| `fastmcp.apps` | `FastMCPApp`, `AppConfig`, `PrefabAppConfig`, `ResourceCSP` |
| `mount` | `(server, namespace=None, tool_names=None)` — **`prefix` foi removido** |

Que `AzureJWTVerifier` não mudou é o achado mais útil: **o T0 porta sem reescrita**.

## A ordem, e por que não é a numeração

```
Fase 0  o app separado           habilita todo o resto
Fase 1  T5  prompts + resources  barato, e prova o app novo com risco baixo
Fase 2  T6  o selo               o diferencial, e o motivo da Fase 0
Fase 3  T3  escrita + HITL       maior superfície de risco; depois do selo, para nascer auditada
Fase 4  T4  OBO                  substitui caminho existente; exige comparação
Fase 5  T7  escala               tasks, sessions, cache, apps — cada um opcional
```

T5 antes de T6 porque é a fase que prova o app novo com o menor risco possível: se prompts e
resources funcionam lá, a fundação está boa. T3 depois de T6 para a escrita **nascer** com selo e
trilha, em vez de ganhá-los depois.

---

## Fase 0 — o app separado

**Entrega:** `apps/mcp/` sobre FastMCP 4, servindo o mesmo `/mcp` de hoje, com paridade de
comportamento: auth de Resource Server, autorização por papel, `search_docs`. Nenhuma capacidade
nova. O critério é **paridade**, não novidade.

- `apps/backend/pyproject.toml`: a divisão é **cirúrgica, não por família**. Medido: o teto
  `mcp<2` vem do extra `all` do `agent-framework-core`, arrastado pelo meta-pacote
  `agent-framework`. Então vão para `[project.optional-dependencies] agents`:
  `agent-framework` (meta), `agent-framework-ag-ui`, `langchain`, `langgraph`, `langchain-openai`,
  `ag-ui-langgraph`, `deepagents`.
  **`agent-framework-declarative` FICA na base** — ele precisa só do core sem extras, e é o que faz
  os prompts (Fase 1) atravessarem para o app novo. Confirmado por instalação real ao lado do
  `fastmcp==4.0.0b3`.
  Todo lugar que instala o backend passa a pedir `.[agents]`: `Dockerfile`, `compose.yaml`,
  `ci.yml`, `scripts/gates.py`, instruções de dev. **Esquecer um mata o backend no import** —
  falha alta, não silenciosa.
- `apps/mcp/pyproject.toml`: depende do backend por path, **sem** o extra, mais `fastmcp==4.0.0b3`.
- `authz.py` **morre**, mas não vira uma linha: `require_roles` do 4.0.0b3 exige **TODOS** os papéis
  passados (AND). `require_roles("Reader","Author","Approver","Admin", …)` — que era o que a primeira
  versão desta spec previa — faria a tool sumir do `tools/list` para todo mundo, **sem erro**, porque
  tool negada por `auth=` é filtrada, não recusada. O OR ("qualquer um destes papéis") é composto por
  cima: um `require_roles` de biblioteca por papel, e só a composição é nossa. Trave as duas semânticas
  em teste — a diferença é invisível em runtime.
- `httpx` → `httpx2` onde o app novo tocar. Os `except httpx.` viram código morto **silencioso** —
  varredura, não bump.

**Gate:** um job de CI que instala o pacote base **sem** o extra + FastMCP 4 e importa
`app.modules.knowledge.public`. O `import-linter` prova o grafo; só a instalação prova a
instalabilidade, e é ela que quebra.

**A fase foi partida em três, e a razão é de risco.** A versão original desta spec exigia que o
`/mcp` do monolito saísse **no mesmo commit** em que o novo entrasse, para nunca haver duas
superfícies. Na execução isso se mostrou pior: um único commit misturaria mudança de
empacotamento, app novo e remoção — e um vermelho no meio não diria qual das três causou.

O corte que ficou:

- **0a** — o framework de agente vira extra. Nada de app novo; a base fica instalável sem o teto.
- **0b** — nasce `apps/mcp/` com paridade. As duas superfícies coexistem, **de propósito e por pouco
  tempo**, com gates provando que decidem igual (autorização, identidade, ACL, metadata OAuth).
- **0c** — o `/mcp` sai do monolito, e os gates dele são portados **antes** de morrerem.

O risco de duas superfícies é real e continua listado abaixo. A mitigação passa a ser *paridade
provada por gate* em vez de *janela zero* — e a 0c fecha a janela. O que **não** se admite é 0b
mergear sem a 0c: a divergência silenciosa sobre o que o usuário pode ver é o pior desfecho
possível deste projeto.

**Pronto quando (0b):** os gates de MCP passam contra o app novo com as mesmas asserções, e a
metadata OAuth anunciada responde 200 na URL exata que o 401 aponta.

---

## Fase 1 — T5: prompts e resources

**Viável no app novo — medido.** `agentdefs` importa `agent_framework_declarative._models`
(`definitions.py:52`), e esse pacote resolve junto com FastMCP 4. Se ele tivesse exigido o
meta-pacote, esta fase morreria aqui.

**Prompts.** Os documentos AgentSchema em `apps/backend/agents/assured/` já são a fonte única
(ADR-013/015). Publicá-los como `@mcp.prompt` **deriva** dessa fonte — não cria segunda lista. É a
SEGUNDA MÁXIMA de graça.

- `prompts_agentdefs.py` lê `agentdefs.public`. Prompt literal dentro do módulo = PR errado.
- **Gate espelhado**, no mesmo espírito de `tests.registry.domain_registry_test`: a lista de
  prompts do MCP tem exatamente os mesmos ids que `agentdefs` compõe.

**Resources.** O documento integral, como resource template, reautorizando pelo mesmo ACL da rota
`/source`. O FastMCP 4 barra path traversal por padrão (`resource_security` no construtor) — ainda
assim, teste explícito para `..`, caminho absoluto e byte nulo.

**Completion.** `@mcp.completion` para autocompletar domínio e nome de documento.

**Pronto quando:** o gate espelhado passa, e um cliente lista prompts e lê um resource com ACL
aplicada.

---

## Fase 2 — T6: o selo de assurance

**A camada que justifica a separação.** Uma `ServerExtension` com identificador reverse-DNS que
anexa, a cada resposta: citações resolvíveis e o id do evento na trilha (ADR-023). Groundedness
FICA DE FORA, e é uma omissão deliberada, não um esquecimento: não existe groundedness
pré-calculada em `tools/call` para copiar, e calculá-la aqui violaria o princípio da fase — o
selo não calcula nada, só copia o que já existe.

```
identifier = "br.com.rededor.foundry/assurance"   # sem default na classe: obrigatório
settings()               → o que oferecemos, anunciado por capacidade
intercept_tool_call(...) → anexa o selo
```

O identificador do rascunho desta spec (`rededor.com/assurance`) estava **errado por dois
motivos**, corrigidos na execução: era forward-DNS onde a SEP-2133 exige reverso (e a validação
da biblioteca cobra), e `rededor.com` não é o domínio da organização — reivindicar namespace
alheio num identificador que viaja no fio. O segmento `foundry` existe porque um segundo servidor
MCP da organização colidiria, e **colisão de extensão não dá erro**: dá dois selos com
significados diferentes sob a mesma chave.

**O caminho de volta do id do evento não existia, e a forma óbvia não funciona.** Medido: um
`ContextVar` setado dentro do corpo da tool **não é visto** pelo interceptador — o FastMCP roda o
corpo com o contexto copiado. O que funciona é uma **caixa mutável posta antes do `call_next()`**:
o valor desce, as anexações sobem. Daí `audit.public.receipts()`, que recolhe o que `record()` já
devolvia e todo chamador descartava.

**Onde o selo NÃO chega.** `intercept_tool_call` é o único gancho de resposta que a
`ServerExtension` oferece no 4.0.0b3 — envolve `tools/call` e mais nada. O resource
`document://` e a completion ficam sem selo porque **o protocolo não tem o gancho equivalente**,
não porque não mereçam. Se uma versão futura acrescentar, é aqui que entra.

Duas regras que mudam o desenho, e vêm da documentação da própria peça:

1. **O interceptador precisa confirmar opt-in** (`client_settings` / `read_client_extension_settings`)
   antes de mudar o que o chamador recebe.
2. **Extensões não sobem** de servidor montado para o pai — registrar na raiz.

**Depende de:** T2 (citações, já existe) e da trilha (já existe). O selo **não calcula** nada novo:
lê o que os gates já produzem. Se precisar calcular, o desenho está errado.

**Pronto quando:** um cliente que anuncia a extensão recebe o selo; um que não anuncia recebe a
resposta idêntica à de hoje — provado nos dois sentidos.

---

## Fase 3 — T3: escrita com HITL

**O contrato não se rebaixa.** O padrão nativo (`InputRequiredResult`) é aceitar-ou-recusar; o
nosso (ADR-019) é aprovar · **editar** · rejeitar · responder, com gate de papel. O `edit` é a razão
de a ADR existir.

**O desenho:** `InputRequiredResult` carrega o *transporte* (a tool devolve a pergunta e é
rechamada com a resposta); o *vocabulário* continua sendo `hitl.public.decide`. As quatro decisões
viajam no schema do `ElicitRequestFormParams`, não são reduzidas a um booleano.

- A tool de escrita chama `tickets.public.create_ticket` — que agora é limpo (núcleo limpo).
- `require_roles("Approver", "Admin", extract=...)` no gate.
- **Regra 5 do projeto**: a escrita só dispara depois da decisão humana. O teste tem que provar que
  a tool de criação é inalcançável diretamente.
- O estado entre as rodadas é assinado: `request_state_security` no construtor, com chave de ≥32
  bytes igual em todas as réplicas. **Segredo novo para operar** (Key Vault, nunca no repo).

**Pronto quando:** um cliente completa aprovar, editar, rejeitar e responder; e o gate prova que
sem papel nada escreve.

---

## Fase 4 — T4: OBO nativo — **RECUSADA, com medição**

`EntraOBOToken(scopes: list[str]) -> str` seria a dependência de parâmetro para tools que falem
com Graph/Azure em nome do usuário. **Não é adotável neste desenho**, e a razão foi medida na
fonte instalada (`fastmcp==4.0.0b3`), não inferida:

```python
def _find_azure_provider(auth: AuthProvider | None) -> AzureProvider | None:
    if isinstance(auth, AzureProvider):
        return auth
    if isinstance(auth, MultiAuth) and isinstance(auth.server, AzureProvider):
        return auth.server
    return None
```

Testado com o provider real do `apps/mcp` (`build_auth()`): devolve `RemoteAuthProvider`, e
`_find_azure_provider` responde `None` — `EntraOBOToken` então levanta *"requires an AzureProvider
as the auth provider"*.

**O que adotá-lo custaria.** Trocar o Resource Server pelo `AzureProvider`, que exige
`client_secret` e emite tokens próprios: exatamente a **segunda malha de identidade** que o T0
recusou por desenho, e um segredo a mais para guardar (ADR-005).

**O que se perde recusando: nada.** `tenancy` já faz brokering de credencial (OBO para audiência
Microsoft, connections do Foundry no resto) e `knowledge.retrieve` já troca OBO pelo caminho
existente — é ele que faz o trim de ACL acontecer sob a identidade de quem perguntou. Adotar o
`EntraOBOToken` não preencheria lacuna; trocaria uma implementação que funciona por outra que
custa uma malha de identidade.

**Gatilho de reavaliação.** Se o `fastmcp` passar a aceitar `RemoteAuthProvider` (ou expor a troca
OBO sem exigir o proxy), reavaliar — a conveniência da dependência de parâmetro é real. Verificar
com o mesmo teste: `_find_azure_provider(build_auth(...))` deixando de ser `None`.

## Fase 5 — T7: escala — **OS QUATRO ITENS RECUSADOS, com medição**

Quatro coisas independentes; nenhuma é fundação, cada uma entrava sozinha. **Nenhuma entrou.** A
fase não acrescenta superfície: acrescenta quatro medições, quatro gatilhos de reavaliação e
**um gate** — o do único item que fazia dano sem sintoma.

Isto não é o mesmo que "não deu tempo". Cada recusa abaixo tem um número medido no pacote
instalado ou no `infra/`, e o padrão é o da Fase 4: quando a peça de primeira parte não serve,
dizer por que **com prova** vale mais que ligá-la e descobrir depois.

O que atravessa as quatro é uma coisa só, e vale escrever antes delas: **este app roda com
`minReplicas: 0`** (`infra/containerapps.bicep:375`). Ele não é um servidor ocioso caro, é um
servidor que **desliga**. Toda peça de escala do FastMCP 4 assume, por padrão, memória de
processo — e memória de processo, aqui, é memória que some por design entre uma chamada e a
seguinte. A Fase 3 já tinha topado com isso e resolvido do lado certo: o estado da decisão humana
viaja **selado no fio** (`request_state_security`), não guardado aqui.

### 1 · Tasks (`@mcp.tool(task=True)`) — recusada

**Medido**, em venv descartável com `fastmcp[tasks]==4.0.0b3` (arrasta `pydocket 0.24.1`):

- o backend padrão é `memory://` — `DocketSettings.url`, descrito na própria fonte como
  *"In-memory backend (single process only)"*;
- uma task aceita e consultada de um **processo novo** (o modelo fiel do scale-to-zero: a réplica
  morre entre a submissão e o poll) responde `Task <id> not found` — enquanto o cliente recebeu,
  na aceitação, `ttl_ms=900000` e `poll_interval_ms=5000`. Isto é o pior formato possível de
  falha: o servidor **prometeu** 15 minutos de vida e o cliente vai bater na porta 180 vezes
  contra um id que não existe mais;
- sem o extra, `task=True` não degrada — o **handshake do servidor inteiro falha** com
  *"require the tasks extension"*. Falha alta, e é a favor: ninguém liga isto por engano.

**O que adotá-la custaria:** um Redis/Valkey durável na assinatura (recurso Azure novo, com
custo e operação), mais um pacote beta a mais no caminho de deploy.

**O que se ganharia hoje: nada.** Não existe tool lenta neste servidor. `search_docs` é uma busca
e `open_ticket` é uma escrita atrás de HITL. O eval run e a reingestão — que motivavam o item —
**não são tools MCP**: são módulos de CLI do backend (`eval.run_eval`,
`app.modules.knowledge.internal.ingest`). Transformá-los em tools é **superfície de produto
nova** (operação administrativa de escrita exposta por MCP), com decisão própria de papel, trilha
e HITL — não é um item de escala, e entrar por essa porta seria decidi-la sem discuti-la.

**Gatilho de reavaliação:** quando existir uma tool MCP cuja execução passe de ~30s **e** houver
um backend durável já na assinatura por outro motivo. Refazer as duas medições acima — a de
`DocketSettings.url` e a do processo novo — antes de prometer qualquer TTL a um cliente.

### 2 · Sessions (`UserSession`) — recusada

**Medido:** sem `session_state_store`, o servidor cria `MemoryStore()`
(`fastmcp/server/server.py:498`) — estado de processo. Com `minReplicas: 0`, é estado que evapora
por ociosidade.

Mas o argumento decisivo não é esse; é que **o produto não tem o problema**. As superfícies de
leitura são sem estado por desenho, a memória entre sessões já existe no Foundry (memory store,
pelo caminho do backend), e o **único** estado entre chamadas deste servidor — a decisão humana
do `open_ticket` — já é resolvido, e resolvido melhor: ele viaja selado pelo SDK, amarrado ao
principal, ao nome da tool, ao digest dos argumentos e a um TTL, **sem nada guardado aqui**.
Trocar isso por `UserSession` exigiria um armazenamento durável novo para chegar a um resultado
pior: estado do lado do servidor, que a réplica morrendo apaga. `mcp_app/request_state.py`
escreve essa decisão por extenso.

**Gatilho de reavaliação:** quando aparecer estado por usuário que **não caiba no fio** (o caso
típico é um resultado acumulado grande) — e não antes. Se isso acontecer com `minReplicas: 0`
ainda valendo, a resposta continua sendo não: a resposta certa passa a ser o armazenamento
durável que o backend já tem, não um novo.

### 3 · Cache (`cache_ttl` / `cache_scope`) — recusada, **e travada por gate**

Era o item marcado como o único capaz de vazar por configuração (risco 5). A medição desmonta o
risco temido e revela outro, pior por ser silencioso.

**Medido** (`fastmcp 4.0.0b3` + `mcp 2.1.0`):

1. **`tools/call` não é cacheável.** `CacheableMethod` são seis — `prompts/list`,
   `resources/list`, `resources/read`, `resources/templates/list`, `server/discover`,
   `tools/list` — e a chamada de tool não está entre eles. O vazamento que a spec temia (a
   resposta de busca de um chamador servida a outro, com o trim de ACL feito para o primeiro) é
   **impossível por construção**, não por configuração nossa.
2. **O hint é uniforme por construção.** `build_cache_hints` faz
   `dict.fromkeys(get_args(CacheableMethod), hint)`: um valor de servidor para todos os métodos
   cacheáveis. **Não existe "cachear só as listagens"** — ligar o TTL liga junto `resources/read`,
   que aqui é o documento integral controlado por ACL.
3. **O dano real não é vazamento entre pessoas: é buraco na trilha.** Um hint em `resources/read`
   autoriza o cliente a servir a leitura do armazenamento dele. Essa leitura **não chega mais
   aqui**, logo não vira evento (ADR-023) — e o produto continua afirmando que registra toda
   leitura de documento controlado, inclusive as negadas. Uma revogação de acesso, de quebra, só
   passa a valer depois do TTL.
4. **A prova exigida para entrar não é produzível deste lado.** O critério era provar por teste
   que dois chamadores com ACLs diferentes não compartilham entrada de cache. **Não há entrada de
   cache aqui**: o servidor não guarda nada, emite uma dica (SEP-2549) e quem guarda é o cliente.
   `cache_scope="private"` é um pedido, não uma garantia nossa. Sem prova possível, não entra —
   que é a regra da própria fase.
5. **A biblioteca não freia o escopo perigoso.** `cache_ttl=60, cache_scope="public"` constrói
   sem erro e sem aviso; só escopo *sem* TTL é recusado.

**Por que este — e só este — ganhou gate.** As outras três recusas falham alto se alguém as
contrariar (o handshake cai, o `UserSession` levanta, a tool de app sem `auth=` reprova na
matriz). `cache_ttl=300` no construtor é aceito em silêncio. `apps/mcp/tests/cache_hints_test.py`
trava as cinco medições acima e obriga quem quiser ligar cache a passar por elas.

**Gatilho de reavaliação:** quando o FastMCP admitir hint **por método** (aí `tools/list` e
`prompts/list` podem ser cacheados sem tocar `resources/read`), ou quando houver resposta escrita
para o que fazer com a trilha de `resources/read` sob TTL. O gate fica vermelho sozinho se o SDK
tirar `resources/read` da lista de cacheáveis — que é a outra forma de a recusa deixar de valer.

### 4 · MCP Apps (`FastMCPApp`) — recusada

O candidato natural era o card de aprovação, e o FastMCP 4 já traz um pronto
(`fastmcp.apps.approval.Approval`). **Medido**, com `fastmcp[apps]` instalado (`prefab-ui 0.20.2`
resolvido de um `>=0.18.0` — faixa flutuante sobre pacote beta, exatamente o que a spec mandava
pinar):

- o provider registra `request_approval` com **`auth=None`** — medido pelo mesmo `Provider.list_tools`
  que a matriz usa. Adotá-lo como está deixaria `instrumentation_matrix_test` **vermelho**, e com
  razão: seria a primeira superfície deste servidor sem gate de papel do Entra;
- ele é **binário** (Approve/Reject). O contrato deste produto tem quatro decisões, e o `edit` é
  a razão de a ADR-019 existir;
- o desfecho volta como **mensagem de conversa** (`SendMessage`), documentado na fonte como
  aparecendo *"as if the user sent it"*. Isto é: quem interpreta a aprovação passa a ser o
  modelo, sobre um texto, sem papel cobrado e sem evento na trilha — o oposto exato do que a
  Fase 3 construiu.

Um app **próprio** com quatro botões seria possível (`FastMCPApp.ui()` aceita `auth=`), mas é
ergonomia sobre um caminho que já funciona pelo protocolo, paga em dependência beta de faixa
flutuante no caminho de deploy, e nasceria como superfície nova a declarar na matriz.

**Gatilho de reavaliação:** quando `prefab-ui` sair de beta **e** o prefab de aprovação aceitar
`auth=` mais um conjunto de decisões não-binário. Verificar com a mesma medição:
`Provider.list_tools` sobre `Approval()` deixando de devolver `auth=None`.

**Fora de escopo sem ADR:** o gateway sobre MCP de terceiros. Reexpor tool de outro sob a nossa
marca é decisão de responsabilidade, não de engenharia. **Não foi avaliado nesta fase.**

---

## Contratos que nenhuma fase pode quebrar

| Regra | O que significa aqui |
|---|---|
| #1 | nenhuma assinatura inventada — a tabela acima foi medida; o que não foi, mede-se antes |
| #4 | toda resposta que FUNDAMENTA traz citação. `search_docs` traz; `open_ticket` **não cita**, e corretamente — ela não fundamenta nada, e um `[]` afirmaria que tentou |
| #5 | escrita só após aprovação humana com papel (Fase 3) |
| #6 | acesso é DADO; nenhuma classificação nova em código |
| #8 | fronteiras: `public.py` é a única superfície; `import-linter` cobra |
| ADR-005 | nunca guardar segredo — inclui a chave do `request_state_security` |
| ADR-023 | todo evento relevante na trilha, com o ator certo |

## Riscos, com tamanho conhecido

1. **A migração do extra** toca cinco lugares que instalam o backend. Falha alta, mas larga.
2. **Beta em produção:** `fastmcp==4.0.0b3` e `prefab-ui`. Pin exato, sempre.
3. **`httpx` → `httpx2`:** os `except httpx.` viram código morto silencioso.
4. **Duas superfícies MCP** entre a 0b e a 0c — mitigado por paridade provada em gate, não por
   janela zero (ver Fase 0). A 0b **não pode** mergear sem a 0c.
5. **Cache com ACL** (Fase 5): escopo errado vaza documento entre usuários. É o único item desta
   spec que pode causar vazamento por configuração.
   **Fechado na Fase 5, e o risco medido não era esse** — `tools/call` não é cacheável, então a
   resposta de busca nunca entra em cache; o que o TTL alcança é `resources/read`, e o dano é
   buraco na trilha, não vazamento. Ver "Fase 5 · item 3"; o freio é
   `apps/mcp/tests/cache_hints_test.py`.

## O PR de release

Uma branch (`release/mcp-t3-t7`), um PR, **um commit por fase** — cada um revertível sozinho e com
os gates verdes no momento em que entra. Rebase na `main` a cada fase. O corpo do PR é mantido como
changelog, e cada fase acrescenta a sua linha quando fecha.

Isto contraria o `CONTRIBUTING.md` ("keep PRs small and focused"), por decisão explícita do dono do
projeto: o alvo é um PR de release, não seis PRs de feature.
