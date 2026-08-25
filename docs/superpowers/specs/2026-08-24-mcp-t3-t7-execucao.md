---
title: 'Execução: T3–T7 do MCP sobre o app separado (FastMCP 4)'
description: Do endpoint com uma tool de leitura ao produto — prompts e resources derivados da fonte única, o selo de assurance como extensão de protocolo negociada, escrita atrás do contrato de decisão de quatro opções, OBO nativo, e a camada de escala. Cada API citada foi lida do pacote 4.0.0b3 instalado, não da documentação.
type: design
audience: contributor
status: draft
updated: 2026-08-24
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
| `require_roles` | `(*roles: str, extract: Callable[[dict], Iterable[str]]) -> AuthCheck` — `extract` é **obrigatório**, não tem default |
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

- `apps/backend/pyproject.toml`: `agent-framework*`, `langchain*`, `langgraph`, `deepagents`,
  `ag-ui-*` saem de `dependencies` e entram em `[project.optional-dependencies] agents`.
  Todo lugar que instala o backend passa a pedir `.[agents]`: `Dockerfile`, `compose.yaml`,
  `ci.yml`, `scripts/gates.py`, instruções de dev. **Esquecer um mata o backend no import** —
  falha alta, não silenciosa.
- `apps/mcp/pyproject.toml`: depende do backend por path, **sem** o extra, mais `fastmcp==4.0.0b3`.
- `authz.py` **morre**: `require_roles("Reader", extract=lambda c: c.get("roles") or [])` substitui
  a ponte escrita à mão. Atenção ao `extract` obrigatório.
- `httpx` → `httpx2` onde o app novo tocar. Os `except httpx.` viram código morto **silencioso** —
  varredura, não bump.

**Gate:** um job de CI que instala o pacote base **sem** o extra + FastMCP 4 e importa
`app.modules.knowledge.public`. O `import-linter` prova o grafo; só a instalação prova a
instalabilidade, e é ela que quebra.

**Pronto quando:** os quatro gates de MCP de hoje passam contra o app novo, e o `/mcp` do monolito
sai do ar no mesmo commit em que o novo entra — duas superfícies servindo a mesma tool é a
divergência que este repositório mais teme.

---

## Fase 1 — T5: prompts e resources

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
anexa, a cada resposta: citações resolvíveis, groundedness, e o id do evento na trilha (ADR-023).

```
identifier = "rededor.com/assurance"     # sem default na classe: obrigatório
settings()               → o que oferecemos, anunciado por capacidade
intercept_tool_call(...) → anexa o selo
```

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

## Fase 4 — T4: OBO nativo

`EntraOBOToken(scopes: list[str]) -> str` como dependência de parâmetro, para tools que falem com
Graph/Azure em nome do usuário.

**A condição:** só entra se **substituir** o brokering que `tenancy` já faz no escopo MCP. Em
paralelo, seriam duas respostas para "quem sou eu lá embaixo" — e a ADR-005 (nunca guardar segredo)
vale para as duas.

**A medir antes de prometer:** o `EntraOBOToken` funciona com `RemoteAuthProvider` (o nosso caminho)
ou só com `AzureProvider` (proxy)? A documentação apresenta OBO como extensão do proxy. **Se só
funcionar com proxy, a fase morre aqui** — adotar o proxy custaria a segunda malha de identidade
que o T0 recusou de propósito.

---

## Fase 5 — T7: escala

Quatro coisas independentes; nenhuma é fundação, cada uma entra sozinha.

- **Tasks** (`@mcp.tool(task=True)`, extra `[tasks]`): para eval run e reingestão. Backend padrão é
  em memória e este produto roda com réplicas — **exige Redis/Valkey durável** antes de prometer.
- **Sessions** (`UserSession`: `get`/`set`/`delete`/`clear`/`end`/`id`): exige auth (já temos).
  Padrão é process-local; com réplicas, `session_state_store` compartilhado.
- **Cache** (`cache_ttl`, `cache_scope`): barato, mas atenção — cachear resposta de busca com ACL
  exige que o escopo seja **por usuário**, nunca `public`. Errar aqui vaza documento entre pessoas.
- **MCP Apps** (`FastMCPApp`): o card de aprovação e a tabela de evidências como UI no cliente.
  ⚠️ `prefab-ui` é beta com breaking changes; **pin exato antes de qualquer deploy**.

**Fora de escopo sem ADR:** o gateway sobre MCP de terceiros. Reexpor tool de outro sob a nossa
marca é decisão de responsabilidade, não de engenharia.

---

## Contratos que nenhuma fase pode quebrar

| Regra | O que significa aqui |
|---|---|
| #1 | nenhuma assinatura inventada — a tabela acima foi medida; o que não foi, mede-se antes |
| #4 | toda resposta com citação — vale para as tools novas também |
| #5 | escrita só após aprovação humana com papel (Fase 3) |
| #6 | acesso é DADO; nenhuma classificação nova em código |
| #8 | fronteiras: `public.py` é a única superfície; `import-linter` cobra |
| ADR-005 | nunca guardar segredo — inclui a chave do `request_state_security` |
| ADR-023 | todo evento relevante na trilha, com o ator certo |

## Riscos, com tamanho conhecido

1. **A migração do extra** toca cinco lugares que instalam o backend. Falha alta, mas larga.
2. **Beta em produção:** `fastmcp==4.0.0b3` e `prefab-ui`. Pin exato, sempre.
3. **`httpx` → `httpx2`:** os `except httpx.` viram código morto silencioso.
4. **Duas superfícies MCP** durante a Fase 0 — mitigado por retirar a antiga no mesmo commit.
5. **Cache com ACL** (Fase 5): escopo errado vaza documento entre usuários. É o único item desta
   spec que pode causar vazamento por configuração.

## O PR de release

Uma branch (`release/mcp-t3-t7`), um PR, **um commit por fase** — cada um revertível sozinho e com
os gates verdes no momento em que entra. Rebase na `main` a cada fase. O corpo do PR é mantido como
changelog, e cada fase acrescenta a sua linha quando fecha.

Isto contraria o `CONTRIBUTING.md` ("keep PRs small and focused"), por decisão explícita do dono do
projeto: o alvo é um PR de release, não seis PRs de feature.
