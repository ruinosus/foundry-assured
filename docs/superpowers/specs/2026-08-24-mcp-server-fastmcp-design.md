---
title: 'Design: um MCP server nosso, dentro do monolito — T0 a T7'
description: Publicar as capacidades do produto (busca com ACL por documento, escrita atrás de HITL, prompts AgentSchema, trilha de auditoria) como um MCP server autenticado por Entra, montado dentro do FastAPI que já existe. Sete camadas, da fundação à extensão de protocolo que carrega o nosso selo de assurance. Cada peça citada foi verificada contra o pacote instalado, não contra a documentação.
type: design
audience: contributor
status: draft
updated: 2026-08-24
---

# Um MCP server nosso, dentro do monolito

## A ideia, em uma linha

Qualquer cliente MCP — Claude, Copilot, VS Code, ChatGPT — se autentica com o **mesmo token
Entra** que a nossa interface já usa e ganha acesso às capacidades do produto: buscar com
**trim de ACL por documento**, ler o documento integral reautorizado, abrir chamado **só depois
de aprovação humana**, e receber de volta um **selo de assurance** — citação resolvível,
groundedness, id do evento na trilha.

O que estamos publicando não é "mais um MCP server de busca". É a **camada de garantias** —
que é a única parte deste repositório que a máxima maior autoriza a ser nossa.

## Por que isto não viola a MÁXIMA MAIOR

O teste do repositório é: *estou expondo uma capacidade a um perfil que não a alcança, ou
reimplementando a capacidade?*

Um MCP server é **superfície de acesso**, não capacidade nova. O Foundry expõe agente e KB para
quem tem RBAC no Azure e abre o portal. Um endpoint MCP expõe as mesmas coisas para quem vive
dentro do próprio editor ou do próprio chat e nunca vai abrir portal nenhum. É a mesma frase que
justifica o produto inteiro:

> "Não é recriar nada da Microsoft, é preencher lacunas e trazer outros perfis de usuário para
> consumir recursos Microsoft."

E o núcleo do transporte **não será nosso**: ele já está pago (ver a seção seguinte). O que
escrevemos é a cola — e uma extensão de protocolo (T6) que carrega o diferencial que já
sobrevive à máxima por decisão explícita.

## O que já está pago — medido no venv, não lido na doc

O SDK oficial `mcp` **já está instalado** neste backend (1.28.0), transitivo do
`agent-framework`. Ele traz mais do que a discussão costuma supor:

| Capacidade | Onde, no pacote instalado | Observação |
|---|---|---|
| Servidor com `@tool`/`@resource`/`@prompt` | `mcp.server.fastmcp.FastMCP` | é o FastMCP v1, doado ao SDK oficial |
| OAuth completo (authorize · token · register · revoke · metadata) | `mcp/server/auth/handlers/` | + middleware `bearer_auth`, `client_auth`, `auth_context` |
| **Resource Server (RFC 9728)** | `mcp/server/auth/routes.py:209` | `/.well-known/oauth-protected-resource` — é o modo certo para pôr o Entra na frente |
| Tasks | `mcp.server.experimental` | `task_support`, `task_scope`, `task_context`, `session_features` |
| Elicitation | `mcp.server.elicitation` | |

E o `agent-framework` **já publica agente como MCP server**: `Agent.as_mcp_server()`
(`agent_framework/_agents.py:1633`). Li o corpo: ele expõe o agente como **uma única tool**,
sobre o `mcp.server.lowlevel.Server`, **sem auth, sem resources, sem prompts, sem autorização
por papel**. Cobre "publicar um agente"; não cobre nada do que esta spec descreve.

**Conclusão da verificação:** existe base oficial para o núcleo. O que o FastMCP acrescenta —
e o que justifica a dependência — é a camada declarativa por cima: autorização por componente,
providers Entra prontos (inclusive troca OBO), composição por namespace, `from_fastapi`, MCP
Apps e, no 4.x, o sistema de extensões.

## A restrição que define a versão — medida no PyPI

```
fastmcp 4.0.0b3        →  mcp>=2.0,<3      +  httpx2>=2.5
agent-framework-core 1.14.0        →  mcp>=1.24.0,<2     ← teto
agent-framework-foundry-hosting    →  mcp>=1.24.0,<2     ← teto
```

**FastMCP 4 e o agent-framework não coexistem no mesmo venv hoje.** Conflito de resolvedor,
não aviso.

```
fastmcp 3.4.7 (estável) →  mcp>=1.24.0,<2  +  httpx<1.0,>=0.28.1  +  starlette>=1.0.1
```

Instalado num venv descartável para conferir: `fastmcp 3.4.7` resolve com `mcp 1.29.0`,
`httpx 0.28.1`, `starlette 1.6.0`, `pydantic 2.13.4` — todos compatíveis com o que este backend
já tem (`fastapi 0.133.0`, `starlette 1.3.1`, `httpx 0.28.1`, `pydantic 2.14.0a1`).

**Decisão:** construir sobre **3.4.7 in-process agora**; migrar para o 4 quando o
`agent-framework` subir o teto do `mcp`. O guia oficial de upgrade 3→4 vira o mapa dessa
migração, e os pré-requisitos dele (`fastapi>=0.133`, `starlette>=1.0.1`, `pydantic>=2.12`)
**já estão satisfeitos** — o custo do salto, quando vier, é `httpx`→`httpx2` e os pontos
listados em cada camada abaixo.

## Matriz de disponibilidade — verificada por introspecção do 3.4.7

Instalado `fastmcp==3.4.7` num venv isolado e inspecionadas as assinaturas reais:

| Peça | 3.4.7 | Nota |
|---|:--:|---|
| `FastMCP(auth=, middleware=, providers=, transforms=, tasks=, session_state_store=)` | ✅ | `cache_ttl`/`cache_scope` **ausentes** (4.x) |
| `@mcp.tool(auth=, app=, task=, tags=, timeout=)` | ✅ | |
| `@mcp.resource(auth=, app=)` · `@mcp.prompt(auth=)` | ✅ | |
| `require_scopes(*scopes)` · `restrict_tag(tag, scopes=[...])` · `AuthContext(token, component)` | ✅ | |
| `require_roles(..., extract=...)` | ❌ | "novo em v4.0.0" |
| `InsufficientScopeError` | ❌ | 4.x — `fastmcp.exceptions` tem `AuthorizationError` |
| `AzureProvider` · `AzureJWTVerifier` · `EntraOBOToken` | ✅ | `fastmcp.server.auth.providers.azure` |
| `RemoteAuthProvider` · `OAuthProxy` · `OIDCProxy` · `JWTVerifier` · `MultiAuth` | ✅ | |
| `get_access_token()` · `CurrentAccessToken` · `TokenClaim` | ✅ | `fastmcp.server.dependencies` |
| `AuthMiddleware` · `Middleware` · `MiddlewareContext` | ✅ | |
| Providers: `LocalProvider` `FastMCPProvider` `ProxyProvider` `OpenAPIProvider` `FileSystemProvider` `SkillsProvider` `ClaudeSkillsProvider` `AggregateProvider` | ✅ | |
| `mcp.mount(server, namespace=...)` · `from_fastapi` · `from_openapi` · `add_transform` | ✅ | `prefix=` ainda existe (removido no 4) |
| `http_app(path=, middleware=, stateless_http=, transport=)` · `combine_lifespans` | ✅ | |
| `fastmcp.apps` (`AppConfig`, `PrefabAppConfig`, `UI_EXTENSION_ID`, `ResourceCSP`) | ✅ | Prefab vem no extra `[apps]` |
| `fastmcp.server.extensions` (`ServerExtension`, `add_extension`) | ❌ | **4.x** — bloqueia T6 |
| `fastmcp.server.sessions` (`UserSession`) | ❌ | **4.x** — `session_state_store` existe, a classe não |
| `@mcp.completion` | ❌ | 4.x |

Assinaturas exatas confirmadas:

```
AzureJWTVerifier(*, client_id: str, tenant_id: str, required_scopes: list[str] | None = None,
                 identifier_uri: str | None = None,
                 base_authority: str = 'login.microsoftonline.com')

RemoteAuthProvider(token_verifier: TokenVerifier, authorization_servers: list[AnyHttpUrl],
                   base_url: AnyHttpUrl | str, scopes_supported: list[str] | None = None,
                   resource_base_url: ..., resource_name: ..., resource_documentation: ...)
```

## Arquitetura — onde isto mora

Nenhum app novo. Um **módulo como qualquer outro** (ADR-017), montado pela composition root:

```
apps/backend/app/modules/mcpserver/
  public.py                 build_mcp_app() -> Starlette   ← única superfície importável
  internal/
    server.py               constrói o FastMCP: auth, middleware, providers
    auth.py                 AzureJWTVerifier + RemoteAuthProvider + checks de papel
    tools_knowledge.py      chama app.modules.knowledge.public
    tools_tickets.py        chama app.modules.tickets.public + hitl.public
    resources_docs.py       documento integral, reautorizado por ACL
    prompts_agentdefs.py    os AgentSchema publicados como prompts MCP
    assurance.py            o selo (T6) — extensão no 4.x, `meta` no 3.x
```

Regra que mantém isso honesto e que o `import-linter` vai cobrar: **`mcpserver` não implementa
nada**. Ele traduz `knowledge.public`, `tickets.public`, `hitl.public`, `audit.public`,
`agentdefs.public` para o vocabulário MCP. É a mesma relação que `registry.py` tem com os
domínios — despacho, não lógica.

Montagem, ao lado de `mount_domains(app)` em `app/main.py`:

```python
from app.modules.mcpserver.public import build_mcp_app

mcp_app = build_mcp_app()          # internamente: mcp.http_app(path="/mcp")
app.mount("/mcp", mcp_app)
# e o lifespan do app precisa incluir o do mcp_app (combine_lifespans)
```

**Atenção medida:** `app/main.py` aplica `CORSMiddleware` no app inteiro. A documentação do
FastMCP avisa que CORS no topo, com um MCP autenticado por OAuth montado em prefixo, causa
**404 em rotas `.well-known` e falha em `OPTIONS`**. O padrão documentado é sub-app com
middleware próprio. Isto é um item de projeto, não um detalhe de implementação.

---

# As camadas

Cada camada abaixo é entregável sozinha e testável sozinha. A ordem é de dependência real, não
de preferência.

## T0 — Fundação: o endpoint existe e é autenticado

**O que é.** Um `/mcp` que fala Streamable HTTP, autenticado como **Resource Server**: o
cliente já traz um token do Entra e nós só verificamos assinatura, emissor, audiência e escopo.

**Peças (todas presentes no 3.4.7):**

```python
from fastmcp import FastMCP
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.azure import AzureJWTVerifier

verifier = AzureJWTVerifier(
    client_id=settings.azure_client_id,
    tenant_id=settings.azure_tenant_id,
    required_scopes=["access_as_user"],
)
auth = RemoteAuthProvider(
    token_verifier=verifier,
    authorization_servers=[f"https://login.microsoftonline.com/{tenant_id}/v2.0"],
    base_url=settings.public_base_url,
)
mcp = FastMCP("Foundry Assured", auth=auth)
```

**Por que Resource Server e não `AzureProvider` (OAuth proxy).** O proxy exige
`client_secret` e faz o FastMCP virar um authorization server intermediário — segunda malha de
identidade convivendo com a que já temos. O verifier **não pede segredo nenhum** e reaproveita
exatamente a app registration que o `fastapi-azure-auth` já usa. Menos superfície, mesma
garantia. (Regra do repo: nada de API key hardcoded; auth sempre via credencial do Azure.)

**O que ganhamos.** Um endpoint MCP que qualquer cliente compatível descobre sozinho pelo
`/.well-known/oauth-protected-resource` e no qual ninguém entra sem token do nosso tenant.

**Custo.** Uma dependência nova (`fastmcp==3.4.7`, pin exato), um módulo, uma linha de montagem,
o contrato do `import-linter`, e resolver o CORS.

**Decisões em aberto.** (a) O `identifier_uri`/escopo customizado a expor — reusar
`access_as_user` ou criar `mcp.invoke`? (b) `/mcp` no mesmo host do backend ou host próprio?

**Pronto quando.** Um teste offline sobe o app, faz `tools/list` sem token e recebe 401; com
token válido de teste, recebe a lista. E `tests/smoke/routes_snapshot_test` registra as rotas
novas.

---

## T1 — Autorização: papel do Entra decide quais tools existem

**O que é.** Cada tool declara quem pode chamá-la. Quem não pode **não vê a tool na listagem** —
não é 403 depois, é ausência antes.

**No 3.4.7** (o que existe hoje): `require_scopes(...)`, `restrict_tag(tag, scopes=[...])` e
check próprio sobre `AuthContext`:

```python
from fastmcp.server.auth import AuthContext

def require_role(*roles: str):
    def check(ctx: AuthContext) -> bool:
        if ctx.token is None:
            return False
        return bool(set(roles) & set(ctx.token.claims.get("roles", [])))
    return check

@mcp.tool(auth=require_role("Approver", "Admin"))
def create_ticket(...): ...
```

**No 4.x** isso vira uma linha de biblioteca — e a doc traz o extractor do Entra explícito:
`require_roles("Approver", extract=lambda c: c["roles"])`. Nosso `require_role` é **ponte
temporária, marcada como tal**, não abstração para ficar.

**O que ganhamos.** Os App Roles Admin · Author · Approver · Reader passam a valer no MCP com o
mesmo vocabulário da aplicação, e a regra #5 (escrita só com Approver/Admin) deixa de depender
do call site lembrar.

**Custo.** ~15 linhas de ponte + um teste que prova que a listagem some.

**Decisões em aberto.** Escopo **e** papel, ou só papel? O `platform_ops` hoje usa
*stricter-of-both*; manter a mesma doutrina aqui evita duas regras diferentes para a mesma
pergunta.

**Pronto quando.** Um teste offline com três tokens sintéticos (Reader, Approver, sem papel)
prova: lista diferente para cada um, e chamada direta negada para quem não vê.

---

## T2 — A tool que justifica tudo: busca com ACL por documento

**O que é.** `search_docs(domain, query)` chamando `knowledge.public`, com o trim de ACL
acontecendo **sob a identidade do chamador**, exatamente como no caminho grounded.

**Peça exata.** `get_access_token()` de `fastmcp.server.dependencies` dá o token do chamador
dentro da tool; ele alimenta o mesmo caminho de recuperação que os domínios já usam.

**O contrato que não pode quebrar** (regra #6): controle de acesso é **dado** — os grupos de
leitura declarados na fonte. Nada de classificação nova aqui. Documento sem acesso declarado
continua *fail-closed*. Se um domínio declara `document_access="acl"`, o MCP reautoriza; se
declara `"session"`, a sessão válida é a regra inteira — a mesma tabela do `registry.py`, lida,
nunca reescrita.

**O contrato que não pode quebrar** (regra #4): toda resposta carrega ao menos uma citação.
Aqui isso vira formato de retorno, não recomendação.

**O que ganhamos.** A capacidade que ninguém expõe por MCP: busca corporativa que respeita
permissão **por documento**, dentro do editor do usuário.

**Custo.** A tradução do resultado para o vocabulário MCP (conteúdo + citações estruturadas).

**Decisões em aberto.** O retorno é texto com citações embutidas, ou `structured_content` com
lista de fontes? A segunda é melhor para máquina e pior para clientes antigos.

**Pronto quando.** O gate de controle de acesso (`eval/access_control_test`) roda **também**
pelo caminho MCP e continua com zero vazamento entre grupos. Sem isso, T2 não sobe.

---

## T3 — Escrita governada: HITL antes de `create_ticket`

**O que é.** A tool de escrita não escreve. Ela **propõe** e para; a decisão humana volta e só
então o ticket nasce. É a regra #5 e o gate estrutural do helpdesk, exportados.

**A decisão de arquitetura que esta camada carrega.** Existem dois padrões e eles não são
equivalentes:

1. **Nativo do protocolo (4.x):** `InputRequiredResult` — a tool devolve a pergunta e é
   rechamada com a resposta em `ctx.input_responses`. Funciona sem sessão. Booleano na prática:
   aceita ou não.
2. **Nosso contrato (ADR-019):** aprovar · **editar** · rejeitar · responder, com gate de papel.
   Mais rico, e o `edit` é justamente o que a ADR diz que o booleano não cobre.

No 3.4.7 o caminho viável é **duas tools**: `propose_ticket` (devolve a proposta + um
`proposal_id`) e `decide_ticket(proposal_id, decision, edits)` — que é o mesmo *return-and-resume*
escrito à mão, e que sobrevive à migração para `InputRequiredResult` sem mudar o contrato de
negócio.

**O que ganhamos.** Escrita auditável a partir de qualquer cliente MCP, sem afrouxar o gate.

**Custo.** Um armazenamento curto de proposta (a mesma ideia do `hitl` de hoje) e o cuidado de
**nunca** aceitar `decide_ticket` de quem não tem papel.

**Decisões em aberto.** A proposta expira? Onde ela mora (memória do processo não serve com
múltiplas réplicas)?

**Pronto quando.** Um teste prova que `create_ticket` é inalcançável diretamente e que
`decide_ticket` com papel insuficiente falha antes de tocar o `tickets.public`.

---

## T4 — Identidade downstream: OBO sem escrever OBO

**O que é.** Tools que precisam falar com Graph/Azure em nome do usuário recebem o token trocado
como **dependência de parâmetro**:

```python
from fastmcp.server.auth.providers.azure import EntraOBOToken

@mcp.tool
async def my_calendar(
    graph_token: str = EntraOBOToken(["https://graph.microsoft.com/Calendars.Read"]),
) -> list[dict]: ...
```

**O aviso antes de adotar.** `tenancy` já faz brokering de credencial hoje (OBO para audiência
Microsoft, connections do Foundry no resto) e **nunca guarda segredo** (ADR-005). Adotar o
`EntraOBOToken` só se ele **substituir** aquele caminho no escopo MCP — nunca em paralelo, ou
teremos duas respostas para "quem sou eu lá embaixo".

Restrição documentada: escopos pedidos por `EntraOBOToken` precisam estar em
`additional_authorize_scopes` na inicialização, e OBO exige **admin consent** no tenant
(`AADSTS65001` sem ele).

**O que ganhamos.** Tools de ops no MCP com a identidade do usuário, sem novo código de troca.

**Custo.** Consentimento no Entra e uma comparação honesta com `tenancy` antes de duplicar.

**Decisões em aberto.** `EntraOBOToken` funciona com `RemoteAuthProvider` (T0) ou só com
`AzureProvider` (proxy)? **Isto precisa ser medido antes de prometer** — a doc apresenta OBO
como extensão do proxy.

---

## T5 — Superfície rica: resources, prompts e o fim da segunda lista

**Resources.** O documento integral, exposto como resource template, **reautorizando pelo mesmo
ACL** que a rota `/source/{domain}/{name}` já aplica. O FastMCP 4 barra path traversal por
padrão em templates; no 3.4.7 essa validação é nossa e precisa de teste explícito (`..`,
caminho absoluto, byte nulo).

**Prompts — o item mais barato e mais alinhado do lote.** Os documentos AgentSchema em
`apps/backend/agents/assured/` já são a fonte única das instruções (ADR-013/015). Publicá-los
como `@mcp.prompt` **deriva** dessa fonte; não cria lista nova. É a SEGUNDA MÁXIMA cumprida sem
esforço: um só lugar, dois caminhos até ele.

**Regra:** `prompts_agentdefs.py` lê `agentdefs.public`. Se alguém escrever um prompt literal
dentro do módulo `mcpserver`, o PR está errado.

**Completion** (`@mcp.completion`, autocompletar domínio e nome de documento) é **4.x** — fica
registrado como ganho da migração, não como escopo agora.

**Pronto quando.** Um teste prova que a lista de prompts do MCP tem exatamente os mesmos ids que
`agentdefs` compõe — o mesmo tipo de gate espelhado que `tests.registry.domain_registry_test` já
faz para os domínios.

---

## T6 — O selo de assurance como recurso de protocolo

**O que é.** A cada resposta, um bloco com o que nos torna diferentes: citações resolvíveis,
groundedness, id do evento na trilha de auditoria, e qual gate cobriu aquela resposta.

**No 4.x** isso é uma `ServerExtension` — identificador reverse-DNS, negociada por capacidade,
com `settings()` anunciando o que oferecemos e `intercept_tool_call()` anexando o selo. Duas
regras documentadas que valem citar porque mudam o desenho:

- o interceptador **precisa confirmar opt-in** (`context.client_extension_settings(identifier)`)
  antes de mudar o que o chamador recebe;
- extensões **não sobem** de servidor montado para o pai — registrar na raiz.

**No 3.4.7** não há `add_extension`. O equivalente viável é `meta` no retorno da tool (o
parâmetro existe em `@mcp.tool`) mais um `Middleware` próprio. Menos elegante, mesmo conteúdo,
e migra para extensão sem mudar o que o cliente lê.

**Por que isto sobrevive à máxima.** É a exceção calibrada e escrita no `CLAUDE.md`: a camada de
assurance é nossa, foi pesquisada, não há equivalente de primeira parte. O sistema de extensões
é exatamente o lugar que o protocolo reserva para algo assim — usá-lo é o oposto de reimplementar
plataforma.

**Custo.** Depende de T2 e T3 já emitirem os dados do selo. Sem eles, é moldura vazia.

---

## T7 — Escala e composição

Quatro coisas independentes, agrupadas porque nenhuma delas é fundação:

**Tasks.** `@mcp.tool(task=True)` para o que demora — um eval run, uma reingestão. O parâmetro
`task=` **existe no 3.4.7**; o pacote `fastmcp-tasks` (extra `[tasks]`) não estava instalado no
probe, então a checagem é: instalar o extra e confirmar backend durável (Redis/Valkey) antes de
prometer, porque o padrão é em memória e este backend roda com mais de uma réplica.

**Sessions.** `UserSession` é 4.x. O parâmetro `session_state_store` existe no `FastMCP()` do
3.4.7, mas a classe não — **não prometer estado de sessão nesta fase**.

**Cache.** `cache_ttl`/`cache_scope` são 4.x. Fora de escopo.

**Composição / gateway.** `mcp.mount(server, namespace="learn")` e `ProxyProvider` permitem
colocar os MCP servers Microsoft que já consumimos atrás de **um endpoint governado**, com o
nosso ACL e a nossa auditoria por cima. Atrativo e perigoso na mesma medida: reexpor tool de
terceiro sob a nossa marca precisa de decisão explícita sobre responsabilidade e sobre o que a
trilha registra. **Não entra sem ADR.**

**MCP Apps** (`fastmcp.apps`, extra `[apps]`). Os providers prontos mapeiam quase 1:1 no que já
temos — `approval` é o nosso card de HITL, `form`, `choice`, `file-upload`, e uma tabela para o
painel de evidências. O aviso da doc é operacional e sério: **`prefab-ui` é beta com breaking
changes frequentes e precisa de pin exato antes de qualquer deploy**. Trate MCP Apps como
camada opcional sobre T3/T2 — nunca como pré-requisito deles.

---

# Contratos que esta spec não pode quebrar

| Regra | O que significa aqui |
|---|---|
| #1 — não inventar assinatura de SDK | tudo nesta spec foi lido do pacote instalado; o que não foi, está marcado como "precisa medir" |
| #4 — toda resposta com citação | formato de retorno de T2, coberto pelo gate de policy |
| #5 — `create_ticket` só após aprovação humana com papel | T1 + T3, testados |
| #6 — controle de acesso é DADO | T2 lê `DomainSpec`/manifesto; nenhuma classificação nova |
| #8 — fronteiras verificadas | `mcpserver/public.py` + `internal/`, contrato no `importlinter.toml`, entrada no coverage test |
| #9 — nunca contar `parents[N]` | qualquer caminho ancora em `Path(app.__file__)` |
| ADR-005 — nunca guardar segredo | T0 sem `client_secret`; T4 só se substituir o brokering existente |

# Riscos, com o tamanho conhecido

1. **CORS no app inteiro** quebra `.well-known` e `OPTIONS` do MCP com OAuth. Custo: reorganizar
   para sub-app. Conhecido antes de começar.
2. **Beta e pin.** `fastmcp==3.4.7` é estável, mas o alvo (4.x) é beta com pin exato — o mesmo
   padrão que já mordeu este repo com `agent-framework-declarative==1.0.0rc2`.
3. **O salto para o 4** traz `httpx`→`httpx2`, e os `except httpx.` viram **código morto
   silencioso**. Quando vier, é varredura, não bump.
4. **Duas superfícies para a mesma capacidade.** Se `search_docs` divergir do caminho grounded,
   teremos duas respostas para a mesma pergunta. Mitigação: `mcpserver` chamar o `public` do
   `knowledge`, nunca reimplementar recuperação.
5. **Valores de argumento em header.** No protocolo moderno, método, alvo e **valores de
   argumento** viajam como headers HTTP para roteamento. Isso entra em log de gateway e APM com
   a mesma facilidade que querystring. Precisa de decisão de telemetria antes de expor tool que
   receba dado sensível.

# O que fica de fora, de propósito

- Servidor MCP separado, em outro container — só se o teto do `mcp` no `agent-framework` não
  subir e T6 virar bloqueante. A maioria dos nossos módulos importa `agent_framework`, então um
  venv separado não conseguiria reusá-los; seria duplicação, não isolamento.
- `AzureProvider` como OAuth proxy — segunda malha de identidade sem ganho claro.
- Cache, sessions e completion — 4.x.
- Gateway sobre MCP de terceiros — precisa de ADR própria.

# Perguntas que só o desenvolvedor responde

1. **Escopo de exposição:** o MCP publica só `knowledge` (leitura) na primeira entrega, ou já
   nasce com escrita (T3)?
2. **Escopo Entra:** reusar `access_as_user` ou criar um escopo dedicado ao MCP?
3. **Público:** interno (nosso tenant) ou multi-tenant desde o começo? Se multi-tenant, T0 muda:
   o tenant vem do `tid` e o `AzureJWTVerifier` precisa aceitar mais de um emissor.
4. **T4 (OBO):** substituir o brokering do `tenancy` no escopo MCP, ou deixar fora desta fase?

# Sequência recomendada

```
T0 → T1 → T2   (a primeira entrega defensável: endpoint autenticado, papel valendo, busca com ACL)
   → T3        (escrita governada)
   → T5        (prompts e resources — barato, alto valor de coerência)
   → T6        (o selo; em `meta` no 3.x, extensão quando o 4 entrar)
   → T4 / T7   (OBO, tasks, apps, composição — cada um com sua decisão)
```

T0–T2 é a menor fatia que já é produto. Tudo depois dela é ampliação, não fundação.
