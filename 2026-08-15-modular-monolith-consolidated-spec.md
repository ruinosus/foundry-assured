# Spec — Monolito Modular: Refatoração + Definições Declarativas + Observabilidade (consolidada)

**Data:** 2026-08-15 · **Revisada:** 2026-08-15 (rev. 2) · **Status:** proposto · **Executor:** Claude Code
**Escopo:** `apps/backend` (frontend **inteiramente** fora de escopo na rev. 2 — ver Fase 7)
**Tipo:** refactor estrutural + duas adições controladas (política de aprovação declarativa, fundação OTEL)
**Substitui:** `2026-08-15-modular-monolith-refactor.md` + `2026-08-15-addendum-01-orchestration-observability.md`

## Registro de revisão (rev. 2)

A rev. 1 foi escrita antes de três coisas: o upgrade de framework (agent-framework 1.14.0,
ag-ui 1.1.0, declarative 1.0.2), as ADRs 015/016, e a análise do AHP (Agent Host Protocol).
O diagnóstico da rev. 1 se sustenta; as conclusões de desenho mudaram em cinco pontos.

| # | O que mudou | Por quê |
|---|---|---|
| R-1 | ADR de fronteiras é **017**, não 015 | ADR-015 (AgentSchema substitui o DNA SDK) e ADR-016 (OpenWiki) já existem |
| R-2 | **I-7 reescrito** | o `dna-sdk` saiu do `pyproject.toml`; a fronteira a proteger virou `agents/helpdesk/` + `AGENTS_DIR` |
| R-3 | **Módulo `orchestration` cortado**; Fase 3.5 vira trabalho declarativo | ports para um segundo runtime que não existe = abstração prematura. Ver §2.5 |
| R-4 | **OTEL dividido**: 5.5a antes da Fase 3, 5.5b depois | refatorar sem observabilidade no serving path é refatorar às cegas; snapshot de rota não pega regressão de latência/custo/erro |
| R-5 | **Fase 6 descartada** (era opcional) | medido: 53–88 linhas de código divergentes por par, não "quase idênticos" |

Correções factuais aplicadas ao longo do documento: três arquivos reais sem destino na §2.2
(`agents/definitions.py`, `knowledge/adapt_openwiki.py`, `knowledge/docbundle_schema.py`)
e a lista de gates de CI da Fase 4 (são **oito**, não três).

---

## 0. Contexto e problema

O backend hoje é organizado por camada técnica (`app/{api,services,agents,workflow,core,knowledge,tools}`), não por domínio de negócio. Diagnóstico medido no código atual:

1. **Ciclo de dependência** `app/core ↔ app/agents`: `app/core/tenant_store.py:13` importa `app.agents.mcp.registry.SERVERS`, enquanto todo `app/agents` importa `app/core`.
2. **Domínios de negócio espalhados**: "helpdesk" vive em `workflow/` + `agents/prompts.py` + `tools/tickets.py` + `api/tickets.py` + partes de `services/`; "tenancy" vive em `core/tenant*.py` + `api/tenant.py` + `core/onboarding.py`. Nenhuma pasta corresponde a um conceito de negócio.
3. **`services/` sem coesão**: `graph.py` (Microsoft Graph do admin), `retrieval.py` (query da KB), `grounded.py` (archetype cockpit/selfwiki), `hosted.py` (bridge Responses→AG-UI) e `foundry_evals.py` — cinco responsabilidades de domínios diferentes.
4. **`eval/` (54 arquivos `.py` planos)** mistura: (a) o **harness de assurance** — produto, gate de CI (10 arquivos); (b) **testes** unit/integration/e2e (40); (c) **spikes** descartáveis (`step0_*`, 4).
5. **4 apps `hosted-*` com muita duplicação, mas NÃO intercambiáveis.** Medido (código, ignorando comentários e linhas em branco): `hosted-agent` 77 linhas, `hosted-cockpit` 60, `hosted-platform` 33, `hosted-selfwiki` 65. Divergência por par: 53 (cockpit↔selfwiki) a 88 (agent↔selfwiki). Mesmo o par mais parecido — os dois domínios `grounded` — compartilha só ~36 de ~60 linhas. Ver Fase 6.
6. **Quatro formatos de orquestração de agentes sem abstração comum** (workflow, grounded, tool, hosted) — detalhado na seção 2.5. **Diagnóstico verdadeiro, conclusão revisada:** ausência de abstração comum só é dívida quando há um segundo consumidor. Não há. Ver R-3.
7. **Observabilidade ausente no serving path**: OTEL só existe opt-in no `wiki_builder` (bootstrap App Insights + `enable_instrumentation` + `_CostMeter`); FastAPI/workflow/grounded/platform não exportam nada, apesar de `azure-monitor-opentelemetry` estar no pyproject. Embrião avançado já existente: `cli/provision_eval_rule.py` linka score de eval online ao trace.

**Objetivo:** monolito modular — módulos por domínio, cada um com API pública explícita e internals privados, fronteiras **verificadas em CI** (import-linter) — mais uma fundação de telemetria OTEL no shared kernel (com modelo avançado para HITL, custo e eval) e a migração da política de aprovação/role de tools para os documentos AgentSchema, estendendo a ADR-013 um nível.

**Não-objetivo (rev. 2):** construir uma camada de ports/adapters sobre runtimes de agente. Ver §2.5 para a justificativa e para o gatilho que reabre a decisão.

---

## 1. Invariantes (inegociáveis — herdam as Regras do CLAUDE.md)

- **I-1. Zero mudança de comportamento nas fases de refactor (0–5).** Nenhum endpoint muda de path, verbo, auth ou payload. Nenhum prompt muda. `self_hosted` permanece byte-idêntico em comportamento. Exceções controladas, restritas às fases marcadas: (a) Fase 5.5a/5.5b — o serving path passa a **exportar telemetria** (atrás de env, default no-op); (b) Fase 3.5 — a política de aprovação passa a ser lida de documento em vez de código, com **conjunto de tools gated idêntico** ao de hoje (provado por teste de paridade, ver Fase 3.5). Nada além disso.
- **I-2. Não inventar assinaturas de SDK** (Regra #1 do CLAUDE.md). Vale para `azure-ai-projects`, `agent-framework`, `agent-framework-ag-ui`, `agent-framework-declarative` e OTEL SDKs. Corolário desta revisão: **nenhum adapter especulativo para runtime que não está no repo** — não há stub LangGraph nesta spec (ver §2.5).
- **I-2b. Verificar antes de assumir que uma justificativa antiga ainda vale.** `app/workflow/escalation.py` documenta que o HITL usa `ctx.request_info()` porque `agent-framework-ag-ui 1.0.0rc5` duplicava o `TOOL_CALL_START` de tool com aprovação. O lock hoje tem **ag-ui 1.1.0 / agent-framework 1.14.0**. Nenhuma fase que toque aprovação começa sem essa medição refeita (ver Fase 3.5, passo 0).
- **I-3. Auth sempre `DefaultAzureCredential` / OBO** como está (Regra #2).
- **I-4. Regras de produto intactas**: citação obrigatória no resolver (Regra #4), `create_ticket` só após aprovação HITL com role Approver/Admin (Regra #5), ACL é DADO (Regra #6).
- **I-5. Usar `git mv`** para toda movimentação (preserva history/blame).
- **I-6. CI verde em cada fase.** Workflows que referenciam módulos por path (`eval.access_control_test`, `eval.red_team_test`, `eval.wiki_freshness_test` em `.github/workflows/{security-gates,wiki-freshness,wiki-regen}.yml`) devem ser atualizados **na mesma fase** em que o arquivo se move.
- **I-7. A fonte declarativa dos agentes não muda de forma nem de contrato (ADR-013/014/015).** Concretamente: `apps/backend/agents/helpdesk/` (documentos AgentSchema, `scope.yaml`, `personas/`, `guardrails/`, `eval-cases/`) permanece **onde está e como está**; o seletor `AGENTS_DIR` e o fallback para a cópia baked (ADR-014) continuam funcionando idênticos; `scripts/push-prompts.sh` continua publicando sem rebuild. Se o loader Python (`agents/definitions.py`) se mover, apenas atualize o import — o **caminho dos documentos não é um detalhe interno**, é contrato de deploy (mount read-only do Azure Files em `/mnt/agents`). `.dna/` permanece ferramenta de dev-time e nenhum app depende do `dna-sdk` desde a ADR-015.
- **I-8. Não avançar de fase sem o verde da fase atual.** Cada fase é um commit/PR independente e revertível.
- **I-9. Nada de reescrita oportunista.** Vontade de "melhorar" função durante movimentação → registrar em `docs/superpowers/plans/` como follow-up e NÃO fazer agora.
- **I-10. Telemetria nunca vaza conteúdo protegido.** Conteúdo (prompts/mensagens/args) é opt-in e vai em span *events* com redação; documentos recuperados com ACL trim **nunca** entram em telemetria com conteúdo; identidade pessoal do aprovador fica fora dos spans (só role); toda string `gen_ai.*` vive em `shared/telemetry/conventions.py`.

---

## 2. Arquitetura-alvo

### 2.1 Princípios

- **Módulo = domínio de negócio** (bounded context), não camada técnica.
- Cada módulo tem **`public.py`** (ou pacote `public/`) — única superfície importável por outros módulos — e **`internal/`** — inacessível de fora.
- **Shared kernel mínimo** (`app/shared/`): settings, auth/identidade de request, telemetria. Shared **não importa nenhum módulo**.
- **Composition root** (`app/main.py` + `app/registry.py`): único lugar que enxerga todos os módulos. Regra de dependência em 3 camadas:

```
composition (main.py, registry.py)
        │  pode importar public de todos
        ▼
modules/* ──► apenas app.shared + app.modules.<outro>.public
        │
        ▼
shared/  ──► nada interno ao app
```

- **Comunicação entre módulos**: chamada direta via `public` (in-process). Sem event bus nesta spec — o acoplamento atual é síncrono e funciona; eventos seriam mudança de comportamento (I-1). Candidato a follow-up.
- **Orquestração de agentes**: o `registry.py` com dispatch por `kind` **já é** a casca fina — 176 linhas, espelhado no registry do frontend, com contrato guardado por `eval/domain_registry_test.py`. Não se cria camada de ports sobre ela. O AG-UI já unifica o fio; o que falta unificar é **declaração** (aprovação, role de tool), e isso vai para os documentos AgentSchema, não para Python.
- **Observabilidade**: cross-cutting → shared kernel. Todo span carrega `app.module`, alinhando dashboards às mesmas fronteiras que o import-linter garante.

### 2.2 Estrutura-alvo de `apps/backend`

```
apps/backend/
  app/
    main.py                      # wiring only (imports atualizados; chama setup_telemetry)
    registry.py                  # ← app/domains.py (DomainSpec + mount_domains + _domain_deps)
                                 #   INALTERADO em forma: segue despachando por `kind`
    api_health.py                # ← app/api/health.py (transversal)
    shared/                      # shared kernel — NÃO importa modules/
      __init__.py
      settings.py                # ← app/core/settings.py
      auth.py                    # ← app/core/auth.py
      telemetry/                 # NOVO (Fases 5.5a/5.5b)
        __init__.py              # setup_telemetry(app): idempotente, 1x na composition
        conventions.py           # mapping PINADO das strings gen_ai.* + atributos próprios
        spans.py                 # helpers: agent_span(), tool_span(), approval events, span links
        content_policy.py        # captura de conteúdo OFF por default; ON → span EVENTS
                                 #   com truncamento preservando JSON e redação
        cost.py                  # _CostMeter promovido do wiki_builder: métrica OTEL
                                 #   (tokens por modelo/domínio/tenant) + rollup USD/BRL
    modules/
      tenancy/                   # seam de deployment-mode, resolução/config/store de tenant,
        public.py                #   Connections, entitlement (DomainAssignment), onboarding
        internal/
          tenant.py              # ← app/core/tenant.py
          tenant_store.py        # ← app/core/tenant_store.py (SEM import de SERVERS — ver 2.3)
          onboarding.py          # ← app/core/onboarding.py
        api.py                   # ← app/api/tenant.py
      admin/                     # RBAC + user management (Graph app-only)
        public.py
        internal/
          graph.py               # ← app/services/graph.py
        api.py                   # ← app/api/admin.py + app/api/me.py
      knowledge/                 # ingestão + corpus + wiki + ACL + retrieval (query)
        public.py                # expõe: secure_search, retrieval, helpers de ACL canônicos
        internal/
          ingest.py              # ← app/knowledge/ingest.py
          ingest_docbundles.py   # ← app/knowledge/ingest_docbundles.py
          wiki_builder.py        # ← app/knowledge/wiki_builder.py (passa a consumir
                                 #   shared/telemetry na Fase 5.5a — dedup do bootstrap)
          adapt_deepwiki.py      # ← app/knowledge/adapt_deepwiki.py
          adapt_openwiki.py      # ← app/knowledge/adapt_openwiki.py  [rev.2: faltava na rev.1]
          docbundle_schema.py    # ← app/knowledge/docbundle_schema.py [rev.2: faltava]
          acl_setup.py           # ← app/knowledge/acl_setup.py (promover _canonical/_component
                                 #   a nomes públicos do módulo)
          retrieval.py           # ← app/services/retrieval.py
          secure_search.py       # ← app/agents/secure_search.py
        docbundle.schema.json    # ← app/knowledge/docbundle.schema.json [rev.2: faltava]
        corpus/                  # ← app/knowledge/corpus/
        skills/                  # ← app/knowledge/skills/
      helpdesk/                  # workflow triage→retrieve→resolve→escalate
        public.py                # expõe: build_helpdesk_workflow
        internal/
          graph.py               # ← app/workflow/graph.py
          agents.py              # ← app/workflow/agents.py
          escalation.py          # ← app/workflow/escalation.py — o role-gate Approver/Admin
                                 #   fica AQUI, em código (Regra #5). Ver Fase 3.5, passo 0.
          memory.py              # ← app/workflow/memory.py
          stream_fix.py          # ← app/workflow/stream_fix.py
      grounded/                  # archetype cockpit/selfwiki (Q&A citada)
        public.py                # expõe: stream_grounded + builders dos agentes grounded
        internal/
          grounded.py            # ← app/services/grounded.py
          cockpit.py             # ← app/agents/cockpit.py
          selfwiki.py            # ← app/agents/selfwiki.py
          concierge.py           # ← app/agents/concierge.py
          per_request.py         # ← app/agents/per_request.py (lógica genérica migra p/
                                 #   orchestration na Fase 3.5)
      platform_ops/              # concierge tool-driven sobre MCP servers Microsoft
        public.py                # expõe: SERVERS (catálogo), builder do platform agent
        internal/
          platform.py            # ← app/agents/platform.py
          mcp_registry.py        # ← app/agents/mcp/registry.py
          mcp_tools.py           # ← app/agents/mcp/tools.py
      tickets/
        public.py                # expõe: create_ticket + persistência
        internal/
          tickets.py             # ← app/tools/tickets.py
        api.py                   # ← app/api/tickets.py
      hosted/                    # bridge Responses→AG-UI + endpoints gêmeos hosted
        public.py                # expõe: stream_agui, stream_platform_agui, aclose
        internal/
          hosted.py              # ← app/services/hosted.py
        api.py                   # ← app/api/chat.py
      evaluation/                # harness de assurance COMO PRODUTO no serving (api + cloud evals)
        public.py
        internal/
          foundry_evals.py       # ← app/services/foundry_evals.py
        api.py                   # ← app/api/evals.py
      agentdefs/                 # dono de TODA definição declarativa de agente
        public.py                # ← app/agents/prompts.py (superfície de consumo; ADR-013)
        internal/
          definitions.py         # ← app/agents/definitions.py  [rev.2: faltava na rev.1]
                                 #   loader/compositor AgentSchema (ADR-015). A partir da
                                 #   Fase 3.5 também resolve política de aprovação e role de tool.
  agents/helpdesk/               # INTACTO — documentos AgentSchema (I-7). NÃO se move.
  eval/                          # PERMANECE: harness de assurance = produto (Fase 4)
  tests/                         # NOVO: testes movidos de eval/, organizados por módulo
  cli/                           # permanece (provision_*) — imports atualizados
  importlinter.toml              # NOVO: contratos de fronteira (ver 2.4)
```

> Claude Code tem liberdade nos nomes de arquivo internos (ex.: manter `api/` como pacote com dois routers no admin), mas **não** na topologia módulo/public/internal nem nas regras de dependência.

**Nota de nome (rev. 2).** A rev. 1 chamava este módulo de `prompts` e o descrevia como "re-export". Com `definitions.py` dentro (lacuna corrigida) e com a Fase 3.5 movendo aprovação e role de tool para os documentos, o módulo deixa de ser sobre texto: passa a ser dono de persona, instructions, guardrails, política de aprovação e role gates. `prompts` seria um nome que mente. Se o revisor preferir manter `prompts`, é decisão dele — registre no ADR-017; a topologia não muda.

### 2.3 Quebra do ciclo `core ↔ agents`

Hoje: `app/core/tenant_store.py` importa `SERVERS` de `app.agents.mcp.registry` (validação de referências de connection contra o catálogo de MCP servers).

**Correção (preferida):** o catálogo `SERVERS` passa a viver em `platform_ops/public.py` (é dado do domínio platform). `tenancy` **não** importa `platform_ops`; `tenancy.public` expõe `set_server_catalog(catalog)` (ou o validador recebe o catálogo por parâmetro), e a **composition root** injeta `platform_ops.public.SERVERS` no boot. Resultado: `tenancy` e `platform_ops` independentes; só a composition conhece os dois.

**Alternativa aceitável** (se a injeção complicar): mover a validação de connections que usa `SERVERS` de `tenant_store` para `platform_ops`, deixando `tenancy` agnóstica de MCP. Claude Code decide após ler o uso real; documentar no `ADR-017-module-boundaries.md`.

**Proibido:** manter o import cruzado, ou mover `SERVERS` para `shared/` (não é transversal, é domínio).

### 2.4 Enforcement — `import-linter`

Adicionar `import-linter` como dev-dependency (`uv add --dev import-linter`) e criar `apps/backend/importlinter.toml`:

```toml
[importlinter]
root_packages = ["app"]

# C1 — camadas: shared não sobe; modules não importam composition
[[importlinter.contracts]]
name = "Layers: composition > modules > shared"
type = "layers"
layers = [
    "app.main | app.registry",
    "app.modules",
    "app.shared",
]

# C2 — internals são privados: nenhum módulo importa internal de outro.
# UM contrato 'forbidden' por módulo, no padrão:
[[importlinter.contracts]]
name = "tenancy internals are private"
type = "forbidden"
source_modules = [
    "app.modules.admin", "app.modules.knowledge",
    "app.modules.helpdesk", "app.modules.grounded", "app.modules.platform_ops",
    "app.modules.tickets", "app.modules.hosted", "app.modules.evaluation",
    "app.modules.agentdefs", "app.main", "app.registry",
]
forbidden_modules = ["app.modules.tenancy.internal"]
# ... repetir para cada módulo (admin, knowledge, helpdesk, grounded,
#     platform_ops, tickets, hosted, evaluation, agentdefs) — 10 no total

# C3 — independências que refletem o domínio (mínimo obrigatório):
[[importlinter.contracts]]
name = "tenancy independent of platform_ops"   # a quebra do ciclo (2.3)
type = "independence"
modules = ["app.modules.tenancy", "app.modules.platform_ops"]

[[importlinter.contracts]]
name = "shared imports no modules"
type = "forbidden"
source_modules = ["app.shared"]
forbidden_modules = ["app.modules"]
```

E um step de CI:

```yaml
- name: Architecture gate
  working-directory: apps/backend
  run: uv run lint-imports --config importlinter.toml
```

> Dependências **legítimas entre publics** esperadas (não proibir): `helpdesk → knowledge.public, tickets.public, agentdefs.public`; `grounded → knowledge.public, agentdefs.public`; `platform_ops → agentdefs.public`; `hosted → tenancy.public`; `evaluation → grounded.public/knowledge.public` conforme uso real. Mapear as reais na Fase 1 e registrar no ADR-017.

### 2.5 Orquestração — por que NÃO há módulo `orchestration` (rev. 2)

Motivação da rev. 1 (as-is, ainda verdadeira): quatro formatos de orquestração sem abstração comum —
1. **workflow** (helpdesk): grafo `WorkflowBuilder`; HITL estrutural via `ctx.request_info()` no `EscalationExecutor` (ticket só no `@response_handler`, role-gated); rebuild por request p/ OBO.
2. **grounded** (cockpit/selfwiki): pipeline hand-rolled de 4 estações (OBO → retrieve c/ ACL → síntese → re-emissão AG-UI c/ evento `sources`).
3. **tool** (platform): agente único + toolset MCP por request, filtrado por role, writes atrás de tool-approval; `PerRequestAgent` proxy.
4. **hosted**: bridge Responses→AG-UI.

**Por que a rev. 1 estava errada na conclusão.** Os entregáveis concretos do módulo seriam (a) mover `PerRequestAgent` — **48 linhas, ~24 de código real** — e o dispatch por `kind` (~65 linhas) para trás de ports, e (b) um **adapter LangGraph que levanta `NotImplementedError`**. O stub é o sintoma do problema: a razão de existir da abstração é um segundo runtime que não está no repo, e a própria Fase 8 dizia para implementá-lo "quando um domínio LangGraph entrar de fato". Cinco ports e uma hierarquia de adapters para um consumidor hipotético é abstração prematura — o erro espelhado de refazer plumbing que a Microsoft já resolveu, não o oposto dele.

**AHP não é a abstração que faltava.** O Agent Host Protocol é um protocolo **cliente ↔ host** (sincronização de estado multi-cliente, sessões host-autoritativas, replay, reconnect). Sua doutrina lista como anti-goals explícitos: *"how agents reason, plan, call tools, or manage context"*, *"a required model provider, model router, or credential flow"*, *"a universal backend tool registry or tool schema"*. Mapeando contra os ports que a rev. 1 propunha:

| Port proposto (rev. 1) | AHP cobre? |
|---|---|
| `AgentBlueprint` | não — anti-goal explícito |
| `OrchestrationRuntime.build()` | não — construção de agente fica *abaixo* do host |
| `ToolCatalog` + `PolicyFilter` | não — anti-goal explícito |
| `IdentityContext` (OBO) | não — anti-goal explícito |
| `ApprovalContract` | **parcialmente** — `chat/toolCallConfirmed` + elicitation cobrem a interação; **não** cobrem `required_role` nem `attempt`/`previous_error` |

Um de cinco, parcialmente. Além disso, AHP está em **v0.7.0** (repo criado 2026-03-12, MINOR novo a cada 2–4 semanas) e a própria página de versionamento declara: *"Backwards-incompatible changes to AHP are inevitable"*, com compatibilidade pré-1.0 garantida **só dentro do mesmo MINOR**. A lição das ADRs 008/009/011/012/015 é não refazer o que a Microsoft entregou **e estabilizou** — AHP está entregue e explicitamente não estabilizado. Decisão registrada em `ADR-018`.

**O que os dois repos de referência fazem, empiricamente.** O `github-copilot-agent-framework-example` converte AgentSchema → `GitHubCopilotAgent` em **204 linhas sem nenhum port** (*"This is the whole conversion layer: data in, GitHubCopilotAgent out"*). O `opentag-reference`, que de fato tem dois runtimes, **também não construiu ports** — escreveu um **documento declarativo** (`HostBinding`: agent, protocol, host ref, `policy{sessions,reconnect,confirmations}`) mais uma função de projeção que valida capacidade no load. Quando o segundo runtime chegar aqui, essa é a forma: **mais um documento, não uma hierarquia de classes.**

**O que fica no lugar (Fase 3.5 revisada — declarativa).** O que realmente falta unificar não é construção, é **declaração**:

- Hoje `app/agents/mcp/registry.py` carrega **175 linhas de Python** com `min_role`/`min_role_write` por tool — política de acesso **como código**, quando a Regra #6 do CLAUDE.md diz que controle de acesso é **DADO**.
- O exemplo Copilot mostra o padrão: `approval_required_tools()` (24 linhas) deriva o conjunto gated de **duas fontes no documento** — `approvalMode` do `McpTool` (campo padrão do AgentSchema) e uma extensão namespaced para o que o schema não modela (function tools não têm campo de aprovação).
- Aqui o substrato já existe: prompts são documentos AgentSchema com `metadata.x-foundry-assured`, publicáveis sem rebuild (ADR-014).

Logo: **mover política de aprovação e role de tool para os documentos AgentSchema** é o mesmo movimento da ADR-013, um nível adiante — mais aderente à Regra #6, mais barato e sem nenhuma decisão pendente. É isso, e só isso, que a Fase 3.5 passa a fazer.

**Gatilho que reabre esta decisão:** um segundo runtime entrando de fato no monolito, OU uma segunda superfície de cliente precisando anexar-se a uma sessão viva (handoff de ops, Teams/Slack). Nesse dia, releia esta seção e comece pelo documento de binding, não por ports.

### 2.6 Observabilidade — desenho

**Divisão em 5.5a / 5.5b (rev. 2).** A rev. 1 colocava toda a telemetria no fim, depois do refactor. Isso contradiz o próprio objetivo: a Definition of Done do refactor é "zero mudança de comportamento", e a verificação são snapshot de rotas + comparação de fixtures AG-UI — dois checks **estruturais**, que pegam rota sumida e evento fora de ordem e **não** pegam regressão de latência, custo ou taxa de erro. Refatorar 5.951 linhas sem isso é refatorar às cegas.

A dependência real da rev. 1 (a telemetria de HITL consumir o contrato de aprovação) vale **só para os eventos de aprovação**. A árvore `gen_ai`, o custo e o atributo `app.module` não dependem de nada da Fase 3.5. Logo:

- **5.5a — antes da Fase 3**: bootstrap, `conventions.py` pinado, `content_policy`, `cost.py`, árvore `invoke_agent`→`chat`/`execute_tool`, resource attrs. **Baseline gravado antes de qualquer `git mv`.**
- **5.5b — depois da Fase 3.5**: eventos e métricas de HITL, span links de resume, elo trace↔eval, `docs/OBSERVABILITY.md`.

Custo assumido conscientemente: em 5.5a o atributo `app.module` é carimbado contra a estrutura **antiga** e re-mapeado na Fase 5. É um mapping em um arquivo — barato perto de refatorar sem observabilidade.

**`setup_telemetry(app)`** (idempotente, chamado 1x na composition):
- Exporter por env: `APPLICATIONINSIGHTS_CONNECTION_STRING` → Azure Monitor (reaproveita o padrão do `wiki_builder`, incluindo fallback via `project.telemetry.get_application_insights_connection_string()`); senão `OTEL_EXPORTER_OTLP_ENDPOINT` → OTLP genérico; senão **no-op** (zero infra, como hoje).
- `enable_instrumentation()` do agent-framework + auto-instrumentation FastAPI/httpx.
- Resource attrs: `service.name`, `deployment.environment`, `deployment_mode`.
- Span processor injetando em TODO span: `app.tenant_id`, `app.domain`, `app.module`.

**Convenções (pinadas atrás de mapping):**
- Forma GenAI semantic conventions: `invoke_agent` (topo) → filhos `chat` (cada LLM call) e `execute_tool` (cada tool/MCP), com `gen_ai.request.model`, `gen_ai.usage.input_tokens/output_tokens`, `gen_ai.response.finish_reasons`, nomeação `{operation} {model}`.
- Convenções são pré-1.0 (repo `semantic-conventions-genai`): **pinar versão** em `conventions.py`; strings `gen_ai.*` só por constantes desse arquivo. Migração de nome = 1 arquivo.
- `gen_ai.conversation.id` = `thread_id` do AG-UI. NUNCA inventar fallback (UUID/trace-id/hash) — omitir quando não houver.
- Conteúdo: opt-in por env (`TELEMETRY_CAPTURE_CONTENT`), sempre span events com redação; default OFF (I-10).

**HITL avançado — aprovação como telemetria de primeira classe:**
1. **Nunca segurar span aberto durante a espera humana.** No pedido: evento `approval.requested` com `{approval.action, approval.attempt, approval.required_role, approval.id}` → span do run fecha com status OK e `app.run.outcome = "interrupted_for_approval"`.
2. **Resume = novo trace com SPAN LINK** ao span do pedido (correlação por `gen_ai.conversation.id` + `approval.id`), com evento `approval.granted` | `approval.rejected` carregando `{approver_role, decision_latency}` — identidade pessoal do aprovador fora dos spans (I-10); mapping id-pessoa fica no log de auditoria da aplicação.
3. **Retry visível**: `attempt`/`previous_error` como atributos do evento — o trace conta "aprovado→falhou→re-aprovado". (Padrão absorvido do `write_confirmation.py` do OpenTag, que mantém memória bounded de falhas por `(thread, tool)`; aqui só a **telemetria** desse padrão entra, não o interceptor.)
4. **Métricas HITL** (SLOs do humano no loop): `app.approval.latency` (histograma requested→decided, por domínio/ação/tenant) · `app.approval.pending` (gauge) · `app.approval.decisions` (counter por granted/rejected/expired — taxa de rejeição alta = agente propondo ações ruins, sinal de *qualidade*) · `app.approval.retries` (counter).
5. **Graduação IN→ON the loop**: as métricas acima são o critério objetivo para promover ação de "sempre aprova" a "auto com supervisão". Registrar a intenção; a promoção é follow-up de produto.

**Custo e eval fechando o ciclo:**
- `cost.py` alimentado pelos spans gen_ai (tokens exatos) → métrica por modelo/domínio/tenant; no modo `shared`, insumo direto de billing/entitlement.
- Formalizar o elo trace↔eval iniciado por `provision_eval_rule`: todo registro de eval (offline `eval/run_eval` E online rule) carrega `trace_id` + `gen_ai.conversation.id`. Flywheel: falha em produção (trace) → caso no golden set (`eval/datasets/`). `run_eval` captura o trace_id corrente quando telemetria ativa (campo novo; formato dos datasets não muda).
- Decline off-corpus (Regra #4) emite evento `guardrail.decline` com motivo — declines viram dado de qualidade.

---

## 3. Fases de execução (ordem final, intercalada)

Cada fase: branch própria, commit atômico, CI verde antes da próxima (I-8).

**Sequência rev. 2:** **0 → 1 → 2 → 5.5a → 3 → 3.5 → 4 → 5 → 5.5b**
(rev. 1 era `0 → 1 → 2 → 3 → 3.5 → 4 → 5 → 5.5 → 6 → 7 → 8`)

Fase 6 **descartada** (ver justificativa lá). Fases 7 e 8 permanecem como follow-up fora desta spec.

### Fase 0 — Baseline e rede de segurança
- Capturar baseline: `uv run python -m eval.run_eval --self-test` verde; snapshot da lista de rotas (`tests/smoke/routes_snapshot_test.py` serializa method+path de todas as rotas e compara com fixture commitada).
- Adicionar `import-linter` como dev-dep (só C1 mapeando a estrutura ATUAL, para o tooling rodar).
- 🟢 CI atual verde + snapshot de rotas commitado + `lint-imports` executa.
- 🔴 qualquer teste existente quebrado antes de começar → parar e reportar.

### Fase 1 — Mapa de dependências e ADRs
- Gerar o grafo real de imports (script AST); listar TODAS as dependências entre os futuros módulos.
- **Conferir o inventário contra o disco, não contra esta spec.** A rev. 1 tinha três arquivos reais sem destino (`agents/definitions.py`, `knowledge/adapt_openwiki.py`, `knowledge/docbundle_schema.py` + `docbundle.schema.json`). O gate 🔴 abaixo existe exatamente para isso — aplique-o também à §2.2 corrigida.
- Escrever `docs/adr/ADR-017-module-boundaries.md`: módulos (10), publics, dependências permitidas, decisão 2.3, decisão de nome `agentdefs`/`prompts`, mapa "arquivo antigo → novo" — incluindo a fronteira de `shared/telemetry` (criada na 5.5a, documentada aqui).
- Escrever `docs/adr/ADR-018-no-ahp-for-now.md`: o que o AHP padroniza, por que não é adotado agora (§2.5), e o **gatilho de reavaliação** — AHP 1.0, OU segundo runtime, OU segunda superfície de cliente anexando-se a sessão viva.
- 🟢 ADR-017 e ADR-018 revisáveis; grafo completo; **zero** arquivo `.py` do backend sem módulo de destino (verificar por contagem: todo arquivo em `app/` aparece exatamente uma vez no mapa).
- 🔴 dependência ou arquivo que não se encaixa em nenhum módulo → parar, propor ajuste no ADR antes de mover código.

### Fase 2 — Shared kernel + quebra do ciclo
- Criar `app/shared/`, mover `settings.py` e `auth.py` (git mv), atualizar imports em massa.
- Executar a correção 2.3 (catálogo SERVERS + injeção na composition). O ciclo `core↔agents` morre aqui.
- Ativar contratos C1 e "shared imports no modules".
- 🟢 `lint-imports` verde com C1; app sobe; snapshot de rotas idêntico; `run_eval --self-test` verde.
- 🔴 ciclo persistindo ou `shared` importando qualquer módulo.

### Fase 5.5a — Fundação de telemetria (ANTES do refactor de módulos)
Pré-requisito: Fase 2 (o `shared/` existe). Motivação em §2.6.
1. Criar `shared/telemetry/`: bootstrap generalizado do `wiki_builder` (que passa a consumi-lo — dedup), `conventions.py` com as strings `gen_ai.*` pinadas, `content_policy.py` (default OFF), `cost.py` (`_CostMeter` promovido).
2. Ligar no serving path via composition (`main.py` chama `setup_telemetry`), atrás de env — **default no-op** local (exceção controlada do I-1).
3. Instrumentar o mínimo que serve de rede de segurança para as Fases 3–5: span por request de domínio no `registry.py`, árvore `invoke_agent`→`chat`/`execute_tool`, custo por modelo/domínio/tenant. `app.module` é carimbado contra a estrutura atual e re-mapeado na Fase 5 (custo assumido, §2.6).
4. **Gravar o baseline**: com exporter ligado, rodar o conjunto de smoke/e2e e arquivar latência p50/p95 por domínio, custo por request e taxa de erro. É contra este baseline que as Fases 3–5 se comparam.
- 🟢 sem exporter: app byte-idêntico em comportamento, overhead ~zero; com exporter: árvore visível com `gen_ai.conversation.id`; baseline arquivado e versionado; snapshot de rotas idêntico; fixtures AG-UI idênticas; `run_eval --self-test` verde.
- 🔴 conteúdo de prompt/documento em span *attribute*; string `gen_ai.*` literal fora de `conventions.py`; qualquer divergência de rota/fixture.

### Fase 3 — Módulos, um por PR (menor→maior acoplamento)
Ordem: `tickets` → `admin` → `hosted` → `evaluation` → `knowledge` → `grounded` → `platform_ops` → `tenancy` → `helpdesk` → `agentdefs` → `registry.py`.

Para **cada** módulo:
1. `git mv` para `modules/<m>/internal/` (e `api.py`).
2. Criar `public.py` re-exportando **somente** o que consumidores reais usam (mapa da Fase 1 — nada "por via das dúvidas").
3. Atualizar imports dos consumidores para `app.modules.<m>.public`.
4. Adicionar o contrato C2 do módulo.
5. Rodar: `lint-imports` + boot + snapshot de rotas + `run_eval --self-test` + **comparação contra o baseline da 5.5a** (latência/custo/erro dentro da faixa).

Casos específicos:
- `agentdefs`: leva `prompts.py` **e** `definitions.py`. O diretório `agents/helpdesk/` **não se move** (I-7) — só o loader. Verificar que `AGENTS_DIR` e o fallback baked continuam funcionando antes de fechar o PR.
- `knowledge`: `_canonical`/`_component` viram nomes públicos do módulo (o import de `secure_search` vira interno e legal, mas se forem superfície pública, sem underscore).
- `app/api/__init__.py` deixa de existir: a composition inclui os routers dos módulos + `api_health`. O gate condicional `deployment_mode == "shared"` do router de tenant permanece idêntico, relocado.
- `registry.py` (ex-`domains.py`): mount loop único; imports exclusivamente `*.public`.
- 🟢 por módulo: os 4 checks verdes. 🟢 da fase: `app/{api,services,agents,workflow,core,tools,knowledge}` **não existem mais**.
- 🔴 qualquer `from app.modules.X.internal import ...` fora do próprio X.

### Fase 3.5 — Política de aprovação e role de tool como DADO
Pré-requisito: Fase 3 completa (módulos no lugar, `agentdefs` existe). Justificativa em §2.5.

**Passo 0 — medir antes de desenhar (I-2b).** `escalation.py` justifica o HITL atual por um bug do `agent-framework-ag-ui 1.0.0rc5`; o lock tem **1.1.0**. Rodar o helpdesk com uma tool `approvalMode` nativa e inspecionar o stream AG-UI. Registrar o resultado no PR **antes** de escrever qualquer código:
- **bug morreu** → o `EscalationExecutor` passa a ser uma escolha de desenho, não uma contorna. Registrar no ADR-017 e decidir explicitamente se muda ou fica (recomendação: fica — mudar é I-1).
- **bug vive** → o desenho atual está justificado; anotar a versão contra a qual foi reverificado e seguir.
Em nenhum dos casos esta fase reescreve o HITL. Ela move **declaração**, não mecanismo.

1. Estender o schema dos documentos AgentSchema em `agents/helpdesk/`: `approvalMode` padrão onde o schema suporta (MCP tools) e `metadata.x-foundry-assured.approval` para o que ele não modela (role mínimo por tool, function tools). Seguir o padrão do `github-copilot-agent-framework-example`: extensão **namespaced**, documentada, nunca campo padrão torcido.
2. `agentdefs/internal/definitions.py` passa a resolver essa política e a expor pelo `public.py` (equivalente ao `approval_required_tools()` de 24 linhas do exemplo).
3. `platform_ops/internal/mcp_registry.py` passa a **ler** a política em vez de carregá-la em Python. O `min_role`/`min_role_write` sai do código; o catálogo `SERVERS` (endpoints, dado de infra) fica.
4. `escalation.py` continua com o role-gate `has_role("Approver","Admin")` **inalterado** — é decisão de segurança no serving path, não declaração (Regra #5).
- 🟢 **teste de paridade**: o conjunto `(tool, role_mínimo, exige_aprovação)` derivado dos documentos é **idêntico** ao derivado do `registry.py` de hoje — gerar os dois conjuntos e comparar, sem exceção. `rbac_per_tool_test` e `approval_mode_test` verdes sem alteração de asserção. Snapshot de rotas + fixtures AG-UI idênticos. `prompt_contract_test` estendido para cobrir os campos novos.
- 🔴 qualquer diferença no conjunto de paridade; role-gate saindo do código para o documento; campo padrão do AgentSchema usado para significar coisa diferente do que significa; criação de ports/adapters (§2.5).

### Fase 4 — Separar testes do harness de assurance

> **Correção rev. 2 — a rev. 1 quebrava o CI aqui.** Ela dizia que `eval/` fica com "os três `*_test` que são gates de CI" e mandava `test_attribution` para `tests/knowledge/`. Medido nos workflows, os módulos `eval.*` referenciados são **oito**:
> `access_control_test` · `docbundle_contract_test` · `prompt_contract_test` · `red_team_test` · `run_eval` · `test_attribution` · `wiki_fidelity_test` · `wiki_freshness_test`.
> O critério da rev. 1 estava certo (gate de CI = produto); a lista é que envelheceu. **Antes de mover qualquer arquivo, regenere a lista** — não confie nesta:
> `grep -rho "eval\.[a-z_0-9]*" .github/workflows/ | sort -u`

- `eval/` **permanece** com os 10 arquivos de produto-assurance: `run_eval.py`, `assertions.py`, `__init__.py`, `assurance.yaml`, `datasets/`, `rubrics/`, `README.md` + os oito `*_test` acima.
- Criar `apps/backend/tests/` por módulo — **40 arquivos** (54 `.py` em `eval/` − 10 de produto − 4 spikes): `tests/tenancy/` (tenant_*, connection_*, onboarding_guard, multitenant_scheme), `tests/platform_ops/` (mcp_*, rbac_per_tool, approval_mode), `tests/hosted/` (hosted_build, platform_hosted_bridge), `tests/grounded/` (grounded_*, archetype_emit, retrieval_shape, native_snippet), `tests/registry/` (domain_*, tier_domains), `tests/admin/` (credential_wiring), `tests/knowledge/` (cockpit_acl_stamp, retrieval_acl_parity, dockey_decode), `tests/smoke/` (routes_snapshot da Fase 0), `tests/e2e/` (os `*_e2e_test`, shared_boot_smoke, configured_mode). git mv + imports.
- `step0_*` spikes → `scripts/spikes/` (README de uma linha) — ou deletar se o conteúdo já estiver em docs; verificar referências antes.
- Workflows: `security-gates.yml` e `wiki-*.yml` continuam apontando para `eval.*` (inalterado); qualquer runner apontando para arquivo movido é atualizado no mesmo commit (I-6).
- Convenção de execução permanece (`python -m tests.tenancy.tenant_store_test`); **não** introduzir pytest (I-9, follow-up).
- 🟢 `eval/` só produto-assurance (10 arquivos); testes rodam de `tests/`; **os oito módulos `eval.*` referenciados por workflow continuam resolvendo** (rodar cada um por `python -m`); workflows verdes.
- 🔴 gate de CI quebrado por path desatualizado; qualquer `*_test` referenciado por workflow movido para `tests/`.

### Fase 5 — Hardening do enforcement
- Completar o importlinter.toml: todos os 10 C2, C3 com independências da Fase 1, contratos das dependências permitidas entre publics (ADR-017).
- Re-mapear `app.module` na telemetria para a estrutura nova (o custo assumido na 5.5a, §2.6) — é um arquivo.
- Step "Architecture gate" no CI principal (falha build em violação).
- **Regra #7 no `CLAUDE.md`**: "Fronteiras de módulo são verificadas por import-linter. Novo código entra DENTRO de um módulo existente ou cria módulo novo com public/internal; import cross-module só via `public`. Rodar `uv run lint-imports` antes de commitar."
- Atualizar `README.md` (Repository layout) e `docs/METHOD.md`/diagramas com paths novos.
- 🟢 `lint-imports` estrito verde; grep por `app/services`, `app/workflow`, `app/core/` retorna zero em docs ativos (ADRs históricas podem manter).
- 🔴 contrato afrouxado para "passar" sem justificativa no ADR-017.

### Fase 5.5b — Observabilidade de HITL e o elo trace↔eval
Pré-requisito: Fases 3.5 e 5 completas (política declarativa no lugar; fronteiras estritas ativas). A fundação já subiu na 5.5a.
1. Instrumentar o que faltou: workflow (executors triage/retrieve/resolve na árvore `invoke_agent`→`chat`), grounded (spans retrieve/synthesize, com propagação explícita de contexto OTEL no generator — ver risco na seção 5), platform (`execute_tool` por MCP call), decline (`guardrail.decline`).
2. Modelo HITL da §2.6: evento `approval.requested` fechando o span com `interrupted_for_approval`, resume como novo trace com span link, `approval.granted|rejected` com `approver_role` (nunca identidade pessoal).
3. Métricas HITL (`app.approval.latency|pending|decisions|retries`); elo trace↔eval no `run_eval` (`trace_id` + `gen_ai.conversation.id` em todo registro).
4. `docs/OBSERVABILITY.md` (como ligar, o que é emitido, política de conteúdo/PII, queries de exemplo por `app.module`).
- 🟢 aprovação = evento requested + trace de resume com span link; custo por domínio/tenant consultável; sem exporter: overhead ~zero, app idêntico (no-op); snapshot de rotas idêntico; fixtures AG-UI idênticas.
- 🔴 conteúdo de prompt/documento em span *attribute*; span aberto atravessando espera humana; string `gen_ai.*` literal fora de `conventions.py`; identidade pessoal de aprovador em span; qualquer teste/rota/fixture divergindo.

### Fase 6 — Consolidar `hosted-*` — **DESCARTADA (rev. 2)**
A rev. 1 a propunha como opcional, apoiada em "4 apps quase idênticos". A premissa é falsa. Medido (código, sem comentários/linhas em branco):

| par | linhas divergentes | | tamanho |
|---|---|---|---|
| agent ↔ selfwiki | 88 | `hosted-agent` | 77 |
| agent ↔ cockpit | 83 | `hosted-cockpit` | 60 |
| agent ↔ platform | 76 | `hosted-platform` | 33 |
| platform ↔ selfwiki | 64 | `hosted-selfwiki` | 65 |
| cockpit ↔ platform | 59 | | |
| cockpit ↔ selfwiki | 53 | | |

Mesmo o par mais parecido — cockpit e selfwiki, os dois domínios `grounded` — compartilha só ~36 de ~60 linhas. Consolidar significaria um switch de env sobre quatro corpos genuinamente diferentes, e é a **única fase que toca `azure.yaml` e `azd deploy`**. Payoff: 375 linhas. Risco: o path de deploy dos quatro hosted agents.

**Decisão: não fazer.** Se o assunto voltar, o gatilho honesto é os quatro convergirem sozinhos por outro motivo — não uma consolidação especulativa.

### Fase 7 (opcional — follow-up, não executar nesta spec) — Frontend
- Frontend já é feature-organized; único débito: rotas legadas `/chat` e `/cockpit` (redirects). Registrar como follow-up.
- **Rev. 2: esta spec não muda o frontend.** A rev. 1 previa o ApprovalCard exibindo `attempt`/`previous_error` junto com a Fase 3.5; com a 3.5 revisada (declaração, não mecanismo), não há mudança de frontend. `attempt`/`previous_error` entram só como **telemetria** na 5.5b.

### Fase 8 (futuro — fora desta spec) — Segundo runtime
- Quando um domínio LangGraph/deepagents entrar de fato no monolito, **comece pelo documento de binding**, não por ports — o padrão do `opentag-reference` (`HostBinding`: agent, protocol, host, `policy{sessions,reconnect,confirmations}`, validado no load), não uma hierarquia de adapters em Python. Ver §2.5 e ADR-018.
- Este é também o gatilho que reabre a decisão sobre AHP.

---

## 4. Definition of Done (global)

- [ ] `app/{api,services,agents,workflow,core,tools}` não existem; estrutura = seção 2.2; **todo `.py` do backend tem exatamente um destino** (contagem fechada na Fase 1).
- [ ] Zero ciclos; `lint-imports` estrito verde como gate de CI (10 contratos C2).
- [ ] Snapshot de rotas idêntico ao baseline da Fase 0; fixtures AG-UI (`demo/fixtures/*.json`) com mesmo tipo/ordem de eventos; **latência/custo/erro dentro da faixa do baseline da 5.5a**.
- [ ] Os **oito** módulos `eval.*` referenciados por workflow continuam resolvendo; `security-gates`, `wiki-freshness`, `wiki-regen`, `agent-evals` verdes.
- [ ] `eval/` = produto-assurance apenas (10 arquivos); `tests/` por módulo (40); spikes em `scripts/spikes/`.
- [ ] Política de aprovação e role de tool vivendo nos documentos AgentSchema, com **teste de paridade** provando conjunto gated idêntico ao de hoje; `min_role`/`min_role_write` fora do Python.
- [ ] `agents/helpdesk/` no mesmo lugar; `AGENTS_DIR` + fallback baked + `push-prompts.sh` funcionando (I-7).
- [ ] `shared/telemetry/` ativo atrás de env (default no-op); árvore gen_ai + modelo HITL (eventos + span links + métricas) + custo por tenant/domínio + elo trace↔eval; `docs/OBSERVABILITY.md` escrito.
- [ ] **ADR-017** (fronteiras) e **ADR-018** (não-adoção do AHP + gatilho) escritos; CLAUDE.md com a Regra #7; README/docs sem paths mortos.
- [ ] Nenhum port/adapter de orquestração criado; nenhum stub de runtime ausente do repo (§2.5).
- [ ] History preservado (git mv verificável via `git log --follow` em 3 arquivos amostrais).
- [ ] Fora das exceções declaradas (telemetria + leitura declarativa da política de aprovação), nenhuma linha de lógica de negócio alterada (diff ≈ imports, docstrings de path e re-exports).

## 5. Riscos e mitigações

| Risco | Mitigação |
|---|---|
| Import esquecido quebra boot em runtime (imports lazy: `_domains()` importa prompts dentro da função; `api/__init__.py` condicional) | grep por `from app\.` / `import app\.` a cada fase + smoke de boot + snapshot de rotas |
| CI referencia módulo movido por path | I-6: workflow atualizado no mesmo commit |
| `cli/` e `scripts/*.sh` chamando `python -m app.X` antigo | grep em `cli/`, `scripts/`, `Dockerfile`s, `compose.yaml`, `azure.yaml` |
| Hosted apps importando o backend por path | verificar `apps/hosted-*/main.py` e Dockerfiles antes da Fase 3 |
| Tentação de refatorar lógica junto | I-9 + review de diff: fases 2–4 só moves, imports e re-exports |
| Fase 3.5 alterar o comportamento de aprovação sem querer | **teste de paridade** do conjunto `(tool, role, exige_aprovação)` como gate; a fase move declaração, nunca mecanismo |
| **Justificativa antiga tratada como verificada** (o caso `escalation.py` × ag-ui rc5) | I-2b: toda contorna documentada contra versão de SDK é reverificada contra o lock atual antes de virar premissa de desenho |
| **Lista hardcoded nesta spec envelhecer** (gates de CI, inventário de arquivos) | regenerar do disco/workflows antes de usar — a rev. 1 errou nos dois; Fases 1 e 4 trazem o comando |
| Abstração prematura voltando pela porta dos fundos | §2.5 + DoD: nenhum port/adapter; gatilho explícito para reabrir |
| Volume/custo de telemetria com conteúdo ligado | default OFF; sampling configurável; batching ajustado quando content ON |
| PII/secrets em traces (args de tool, docs ACL, aprovador) | I-10 + `content_policy` com redação; docs ACL-trimmed nunca em telemetria; aprovador = role only |
| Convenções gen_ai mudarem de nome (pré-1.0) | mapping pinado em `conventions.py`; migração = 1 arquivo |
| Spans duplicados (auto-instrumentation do agent-framework + manuais) | manuais só onde o framework não emite (registry, aprovação, grounded pipeline, decline); validar árvore em dev antes do merge |
| SSE/StreamingResponse perdendo contexto OTEL (contextvar já se perde no grounded — verificado no código) | propagação explícita de contexto no generator, mesmo padrão da credencial `_async_credential` |
