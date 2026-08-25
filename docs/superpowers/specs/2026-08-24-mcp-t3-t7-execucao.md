---
title: 'Execução: T3–T7 do MCP sobre o app separado (FastMCP 4)'
description: Do endpoint com uma tool de leitura ao produto — prompts e resources derivados da fonte única, o selo de assurance como extensão de protocolo negociada, escrita atrás do contrato de decisão de quatro opções, OBO nativo, e a camada de escala (tasks, sessão por usuário, cache só das listagens, e a tabela de evidências como MCP App). Cada API citada foi lida do pacote 4.0.0b3 instalado, não da documentação.
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
Fase 5  T7  escala               tasks, sessions, cache, apps — os quatro, cada um opcional
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

## Fase 5 — T7: escala — **OS QUATRO ITENS CONSTRUÍDOS**

Quatro coisas independentes; nenhuma é fundação, cada uma entrava sozinha.

**Esta seção registrava quatro recusas.** Elas foram escritas com medição, e as medições
continuam válidas — estão citadas abaixo, uma a uma, porque cada uma delas virou um requisito do
que foi construído. O que mudou não foi o que o pacote faz: foi a **decisão do dono do projeto**
sobre o custo, com este argumento, que a fase aceita como premissa:

> *"não temos tool lenta agora — mas pode ter, e até as atuais podem ser lentas"*

É um argumento sobre a FORMA do trabalho, não sobre o relógio de hoje, e ele desmonta a recusa
das tasks pela raiz: uma busca contra um índice grande já pode passar do aceitável, e esperar o
sintoma significa decidir no dia em que o cliente já está esperando. Numa releitura, uma das
quatro recusas também estava simplesmente **incompleta** — a do cache, cuja medição parou um
andar acima de onde a resposta estava.

O que atravessa as quatro continua sendo uma coisa só, e vale escrever antes delas: **este app
roda com `minReplicas: 0`** (`infra/containerapps.bicep`). Ele não é um servidor ocioso caro, é
um servidor que **desliga**. Toda peça de escala do FastMCP 4 assume, por padrão, memória de
processo — e memória de processo, aqui, é memória que some por design entre uma chamada e a
seguinte. Por isso o primeiro commit desta fase não liga nada: compra o **Azure Cache for Redis**
(`deployRedis`, Basic C0, ~US$16/mês, `DEPLOY_REDIS=false` desliga) que os itens 1 e 2 exigem.

### 1 · Tasks (`@mcp.tool(task=True)`) — **construída**

**O critério, escrito antes da lista.** Uma tool vira task quando **o tempo dela não é nosso**:
quando o custo dominante é uma chamada a um serviço remoto cuja latência não controlamos e não
podemos limitar sem mentir sobre o resultado. Não vira task por ser importante, e não vira porque
dá.

- **`search_docs` vira.** É uma chamada ao Azure AI Search pelo `retrieve`, sob OBO, contra um
  índice cujo tamanho é do cliente. Nada neste repositório governa esse número.
- **`open_ticket` não vira.** O trabalho dela é um append de milissegundos; quem demora é o
  HUMANO, e o humano já tem a suspensão do SEP-2322. Compor as duas suspensões poria dois
  relógios sobre a mesma espera, e os dois desfechos de um vencer antes do outro são
  inaceitáveis na única superfície de escrita: uma decisão aprovada que não escreve, ou uma
  escrita cujo `requestState` já não vale.
- **`show_evidence` não vira.** Lê a sessão e devolve; não há chamada remota a esperar.

**Sem regressão:** `task=True` é `mode="optional"` — quem escolhe, chamada a chamada, é o
cliente. Uma chamada comum continua síncrona.

**As duas medições da recusa viraram requisito, não obstáculo:**

- `DocketSettings.url = "memory://"` ("single process only") e o processo novo respondendo
  `Task not found` depois de o servidor prometer `ttl_ms=900000` → é por isso que existe backend
  durável, e é por isso que `MCP_REDIS_URL` é condição para as tasks subirem.
- `task=True` sem o extra derruba o handshake → é por isso que a extensão e a tool saem da MESMA
  decisão (`tasks_backend.instalar` devolve o booleano que `register` recebe). Medido de novo
  nesta fase, com precisão maior: a falha é no **lifespan**, não no registro — o cliente nem
  conecta.

**A medição NOVA, e é a que decidiu que o item podia entrar.** O snapshot de contexto que o
pacote grava no backend carrega o **access token do chamador** e os headers dele. Sem
`FASTMCP_TASKS_ENCRYPTION_KEY` ele vai em **JSON claro** (medido, lendo a chave crua do Redis) —
e, pior, `restore_task_snapshot` documenta que sem chave uma falha ao recuperar o snapshot é
**não-fatal: a task roda mesmo assim**, sem a identidade de quem submeteu. Para `search_docs`
isso é o pior defeito que este servidor pode ter — a busca rodando como a aplicação, com o trim
de ACL errado e a trilha gravando `process:app`. Com a chave, qualquer falha de restaurar o
snapshot **falha a task**. A chave não é higiene de segredo com um bônus: é o que faz a task
herdar a garantia de identidade que a chamada síncrona já tinha.

Por isso o código exige **as duas variáveis**, e mede a segunda no **codec que grava**
(`snapshot_codec().protected`) e não na variável de ambiente — o codec decide sobre o singleton
lido no import, e uma leitura nossa divergiria dele exatamente no caso perigoso.

**Gates.** `tests/tasks_backend_test.py` (offline): o critério em forma executável, as duas
variáveis na ordem, o efeito medido no codec, e duas provas por mutação — `task=True` sem
extensão derrubando a conexão, e `memory://` perdendo a task para um subprocesso.
`tests/durability_test.py` (job `mcp-durable`, com Redis): P1 aceita uma task e **morre
abruptamente dentro da sessão**; P2, interpretador novo, a acha pelo id e a vê **terminar**.
Matar graciosamente faria o worker CANCELAR a execução, e o gate ficaria verde sobre o cenário
errado — medido.

### 2 · Sessions (`UserSession`) — **construída**

A recusa anterior dizia que sessão sem caso de uso é infraestrutura para nada. Estava certa: é
por isso que este item e o item 4 são **uma feature**, e entram no mesmo commit.

**O caso de uso.** `search_docs` deposita as citações da busca na sessão do chamador;
`show_evidence` (item 4) as mostra em tabela, sem refazer a busca. Três perguntas decidem se isso
merece estado no servidor:

| pergunta | resposta |
|---|---|
| não cabe no fio? | **Não.** O envelope do `RequestStateBoundary` é amarrado ao NOME DA TOOL e ao digest dos argumentos — estado emitido por `search_docs` é recusado quando devolvido a `show_evidence`. O fio costura duas rodadas da MESMA chamada; isto é outra chamada. |
| não dá para recalcular? | **Não sem mentir.** Refazer a busca consultaria o índice de novo: outra ordem, possivelmente outros documentos. Uma tabela de evidências que discorda da evidência é pior que nenhuma tabela. |
| o que se perde se sumir? | Uma tabela vazia dizendo "nenhuma busca nesta sessão". **A sessão nunca é uma permissão** — papel, tenant e ACL rodam na mesma chamada, sobre o mesmo chamador, como antes. |

**O que não entra na loja:** a pergunta do usuário (conteúdo dela, sem consumidor no destino) e o
conteúdo dos documentos. Só `index`/`source`/`url`, com teto — os três campos que a resposta já
mostrou ao mesmo chamador.

**O TTL, que o FastMCP não impõe.** `Session._save_raw` chama `put` **sem ttl**; a fonte diz que a
retenção é inteiramente da loja. Uma `RedisStore` crua guardaria as citações de cada usuário para
sempre. `TTLClampWrapper(missing_ttl=3600)` é o que o próprio pacote oferece, e o gate põe a loja
crua e a embrulhada lado a lado — `None` contra o prazo.

A medição da recusa (`MemoryStore()` de processo, `server.py:498`) continua valendo e virou o
**modo de repouso declarado**: sem `MCP_REDIS_URL`, a loja é a de processo e a tabela some quando
a réplica dorme. Está escrito no módulo e provado no gate.

**Gates.** `tests/app_evidencias_test.py` (offline) prova o caso de uso ponta a ponta sobre a
pilha HTTP real, com **dois principals**: a tabela de Ana traz as fontes dela, a de Bruno vem
vazia. `tests/durability_test.py` prova a metade que não cabe offline: P1 grava e morre, P2 lê, e
outro principal no mesmo Redis não lê nada.

### 3 · Cache (`cache_ttl` / `cache_scope`) — **construído, só para as listagens**

**A recusa anterior estava incompleta, e o que faltava não era do FastMCP — era do SDK debaixo
dele.** A medição de então era verdadeira: `build_cache_hints` faz
`dict.fromkeys(get_args(CacheableMethod), hint)`, então o atalho do construtor é uniforme e
alcança `resources/read`. A conclusão tirada dali — "não existe cachear só as listagens" — é que
não era. Medido nesta fase, em `mcp 2.1.0`:

```
lowlevel/server.py:421   self.cache_hints: dict[str, CacheHint] = validate_cache_hints(...)
runner.py:357            if (hint := self.server.cache_hints.get(method)) is not None:
```

O mapa é **por método** e o runner o consulta por método. Uniforme é só o ATALHO. Medido no fio,
com um cliente de verdade:

| configuração | `tools/list` | `resources/read` |
|---|---|---|
| `cache_ttl=60` (o atalho) | 60000 | **60000** |
| sem cache nenhum | 0 | 0 |
| mapa por método, sem `resources/read` | 60000 | **0** |

A terceira linha é o que entrou. `resources/read` fica com o **mesmo `ttlMs=0` de antes desta
fase** — não um valor novo, o valor de repouso.

**As três decisões:**

1. **`resources/read` fora.** É a superfície que serve o documento com ACL e cuja chegada aqui é
   o que produz o evento da trilha (ADR-023). Um TTL ali autoriza o cliente a servir a leitura do
   armazenamento dele: a leitura não chega mais, não vira evento, e o produto continua afirmando
   que registra toda leitura. É o dano que a recusa identificou corretamente, e continua sendo
   inaceitável.
2. **Escopo `private`, nunca `public`.** As listagens são filtradas por papel e por tenant;
   `public` autorizaria servir a listagem de um chamador a outro. A biblioteca aceita `public` sem
   erro nem aviso — o freio é o gate.
3. **TTL de 60s**, porque o cache alcança a **vitrine** e nunca a porta: `tools/call` não é
   cacheável, então toda chamada chega aqui e revalida papel, tenant e ACL. O pior caso é ver na
   lista, por até um minuto, uma tool que já não se pode chamar.

**O gate mede o FIO, não o atributo.** Um teste que lesse `mcp._mcp_server.cache_hints` ficaria
verde para sempre se o seam fosse renomeado — o hint sumiria das respostas e o dicionário
continuaria existindo. Três provas por mutação ao lado, porque `ttlMs=0` em `resources/read` seria
indistinguível de "nenhum hint funciona": servidor sem cache (0 é repouso), servidor com o atalho
(alcança `resources/read`), e `cache_scope="public"` aceito em silêncio.

### 4 · MCP Apps (`FastMCPApp`) — **construído, e não na aprovação**

As três medições da recusa continuam válidas e **decidiram onde o app NÃO vai**: o prefab
`fastmcp.apps.approval.Approval` registra `request_approval` com **`auth=None`**, é **binário**
onde o contrato tem quatro decisões (o `edit` é a razão da ADR-019), e devolve o desfecho como
mensagem de conversa — quem interpretaria a aprovação passaria a ser o modelo, sobre um texto, sem
papel cobrado e sem evento na trilha. **Ele não é usado.** `open_ticket` fica exatamente como
estava, com as quatro decisões pelo protocolo.

O app vai onde MCP Apps de fato acrescenta: **mostrar**. `show_evidence` renderiza a tabela das
fontes da última busca — leitura pura, e a cara do produto.

**Duas armadilhas medidas, as duas bloqueantes:**

1. **O renderizador nasceria sem gate, e invisível para a matriz.** Marcada com o placeholder
   `ui://prefab/renderer.html`, uma tool faz o FastMCP **sintetizar** o recurso do renderizador na
   hora de listar, **sem `auth=`** — e a síntese acontece dentro de `FastMCP.list_resources`,
   depois do `super()`, então `Provider.list_resources` (de onde a matriz tira o registro cru)
   devolve `[]` para ele. Seria uma superfície sem gate de papel, legível por qualquer chamador
   autenticado, com o gate de instrumentação **verde**.
   O conserto é apontar a tool para uma **URI nossa** (`_is_prefab_tool` só dispara no placeholder
   literal) e registrar o recurso com o mesmo `require_any_role` do resto — medido: a síntese não
   roda e nenhum recurso sem gate chega a nascer. `FastMCPApp.ui()` **não serve**: ele fixa o
   placeholder no corpo do decorator; o caminho é `mcp.tool(..., app=PrefabAppConfig(resource_uri=…))`.
   O preço, dito: pular a síntese pula também o `rewrite_tool_meta_for_wire`, que remove
   `csp`/`permissions` do meta — a tool leva um `csp` a mais no fio.
   **A matriz passou a enumerar os sintetizados**, com prova por mutação: um servidor descartável
   com `app=True` produz o recurso sem gate, e a descoberta tem que vê-lo.
2. **O renderizador vinha de CDN.** O default manda o cliente buscar CSS e JS em
   `cdn.jsdelivr.net` (471 bytes de HTML, com a versão do `prefab-ui` soldada na URL).
   `mode="bundled"` serve o mesmo renderizador de dentro do wheel: **6,4 MiB**,
   `resource_domains: []`, e **zero** tags que busquem origem externa no parse — medido nos dois
   lados. Sobra uma URL do Pyodide dentro do JS, alcançável só em modo generativo, que este
   servidor nunca emite; o gate a **conta** em vez de afirmar zero.

**O custo, com o agravante que esta mesma fase criou:** 6,4 MiB por leitura, e essa leitura **não
é cacheável aqui** porque o item 3 excluiu `resources/read` para não abrir buraco na trilha. O
renderizador paga a conta de uma decisão que não é sobre ele. Aceito assim — em troca não existe
origem de terceiro no caminho da interface —, e trocável numa constante (`MODO_RENDERIZADOR`).

`prefab-ui` é **pinado exato** (`==0.20.2`) e é dependência obrigatória, não opcional: medido, sem
ele `FastMCPApp` e o decorator constroem **sem erro**, `_build_resource_for_tool` engole o
`ImportError`, e o servidor sobe anunciando um renderizador que ninguém pode buscar. Não há falha
alta para confiar.

**Fora de escopo sem ADR:** o gateway sobre MCP de terceiros. Reexpor tool de outro sob a nossa
marca é decisão de responsabilidade, não de engenharia. **Não foi avaliado.**

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
   resposta de busca nunca entra em cache; o que o TTL alcançaria é `resources/read`, e o dano
   seria buraco na trilha, não vazamento. O cache entrou **sem tocar `resources/read`**, pelo mapa
   por método do SDK, com escopo `private`. Ver "Fase 5 · item 3"; o gate é
   `apps/mcp/tests/cache_hints_test.py`, e ele mede o `ttlMs` que sai no fio.

## O PR de release

Uma branch (`release/mcp-t3-t7`), um PR, **um commit por fase** — cada um revertível sozinho e com
os gates verdes no momento em que entra. Rebase na `main` a cada fase. O corpo do PR é mantido como
changelog, e cada fase acrescenta a sua linha quando fecha.

Isto contraria o `CONTRIBUTING.md` ("keep PRs small and focused"), por decisão explícita do dono do
projeto: o alvo é um PR de release, não seis PRs de feature.
