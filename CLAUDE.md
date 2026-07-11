# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

> **Start with [`AGENTS.md`](./AGENTS.md).** That is the canonical, agent-agnostic
> onboarding surface (an `agents.md/v1` instance read by 28+ tools): the repo map, the
> real build/test/deploy commands, the gitflow, and the `dna sdlc` protocol. This file is
> the **deep, opinionated working rules** — the phases, the SDK-signature discipline, the
> architecture, the non-negotiables. AGENTS.md orients; CLAUDE.md goes deep. The two are
> complementary, not duplicates.

## Estado atual

Repositório **shipped** (v0.6.0): todas as 6 fases do showcase estão verdes (KB, workflow streaming, memória + OBO, HITL, eval, hosted-agent), e por cima delas o **mecanismo de assurance** (build-fidelity → recall → completeness → controle de acesso por documento → red-team).

**Por cima disso, shipou a evolução para SaaS multi-tenant (A→B→C→D, tudo as-built):** um seam de **deployment mode** com três modos — `self_hosted` (single-tenant de hoje, default byte-idêntico), `dedicated` (stamp Azure **Managed Application** + **Lighthouse** na subscription do cliente) e `shared` (multi-tenant real, tenant resolvido por request do `tid` do Entra). **Sub-projeto A** = fundação multi-tenant (`TenantConfigProvider` Single/Multi, resolução de tenant por request + OBO downstream, memória namespaced por tenant, tenant store swappable Azure Table/in-memory). **Sub-projeto B** = `TenantRecord` + `Connection` que **referenciam** connections do Foundry (nunca guarda segredo), API admin `/tenant` + página de Connections. **Sub-projeto C** = brokering de credenciais Microsoft-nativo (OBO p/ servers de audiência Microsoft; Foundry connections caso contrário) + governança de escrita (RBAC por tool, stricter-of-both; tools de WRITE atrás da tool-approval nativa do framework). **Sub-projeto D-runtime** = domínios montam globalmente e são gated por tenant via **DomainAssignment** (entitlement de licença, `enabled_domains`, ADR-010) + endpoint gêmeo `/platform-hosted`. **Sub-projeto D-packaging** = o **platform hosted agent** deployável (Invocations + Foundry Toolbox + OAuth identity passthrough, ADR-011) e o **dedicated stamp** (`infra/managed-app/` + `infra/lighthouse/`, ADR-002). Há um **4º domínio — `platform`**: concierge de ops **tool-driven** sobre MCP servers first-party da Microsoft (Learn, Azure, Entra, ADO, GitHub) com HITL nas ações de escrita.

A fonte de verdade hoje é o código + o [`README.md`](./README.md) e [`docs/METHOD.md`](./docs/METHOD.md) (modelo as-built); a arquitetura-alvo SaaS está em [`docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md`](./docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md), as decisões nas **ADRs 001–011** ([`docs/adr/README.md`](./docs/adr/README.md)), os designs/planos em `docs/superpowers/specs/` + `docs/superpowers/plans/`, e o runbook de empacotamento em [`docs/D-PACKAGING-RUNBOOK.md`](./docs/D-PACKAGING-RUNBOOK.md). A `foundry-helpdesk-spec.md` e a [`docs/ASSURANCE-MECHANISM-PLAN.md`](./docs/ASSURANCE-MECHANISM-PLAN.md) são plano/histórico — leia-as como contexto, não como o estado atual.

## O que é

Showcase do **Microsoft Foundry** — um concierge de suporte de engenharia interno. Dev pergunta no chat → sistema **tria** intenção/urgência → **busca** na base de conhecimento → **redige** resposta fundamentada com citações → **decide** se basta responder ou se precisa de ação (abrir ticket/escalar) com **aprovação humana** → **lembra** preferências e resoluções entre sessões. Tudo **avaliado** (groundedness + rubric + policies) e **rastreável** (OpenTelemetry).

O domínio é **swappable**: a arquitetura "pergunte → fundamente → resolva → escale" vale para qualquer assistente do tipo. Trocar o domínio = trocar o corpus de conhecimento e os prompts. Hoje há **quatro domínios**: três grounded/workflow (helpdesk, cockpit, selfwiki) e um **tool-driven** (`platform`) — concierge de ops sobre MCP servers Microsoft com HITL nas escritas. E roda em **três deployment modes** (`self_hosted`/`dedicated`/`shared`) sobre um único codebase (ver "Estado atual").

## Stack

- **Backend** (Python 3.12): `agent-framework` (agentes + `WorkflowBuilder`), `agent-framework-ag-ui` (adapter AG-UI: `AgentFrameworkAgent`, `add_agent_framework_fastapi_endpoint`), `azure-ai-projects>=2.2.0` (Foundry client: KB, `.beta.memory_stores`, eval), `azure-identity` (`DefaultAzureCredential`), `fastapi`, `uvicorn`. Deps via **`uv`**.
- **Frontend** (Next.js 15, App Router): `@copilotkit/react-core`, `@copilotkit/react-ui`, `@copilotkit/runtime`, com `HttpAgent` apontando para o endpoint AG-UI do backend.
- **Foundry** (provisionar via `azd` + extensão Foundry): project + model deployment (default seguro: **`gpt-5-mini`**), Foundry IQ knowledge base, memory store, Application Insights (tracing OTEL). Foundry **connections** + **Toolbox** sustentam o brokering de credenciais (sub-projeto C) e o platform hosted agent (sub-projeto D-packaging).
- **SaaS multi-tenant** (sobre o mesmo codebase): seam de `DEPLOYMENT_MODE` com `TenantConfigProvider` (Single/Multi), tenant store swappable (Azure Table / in-memory), e — no modo `dedicated` — Azure **Managed Application** + **Lighthouse** (`infra/managed-app/`, `infra/lighthouse/`). Detalhes em "Estado atual".

## Arquitetura (big picture)

Três camadas. O frontend Next.js conversa com o backend Python via **AG-UI sobre SSE**; o backend roda um **workflow multi-agente** que usa o Foundry na nuvem.

- **Frontend** → o "Assurance Console". A rota genérica `/d/[domain]` (ex.: `/d/helpdesk`, `/d/cockpit`, `/d/selfwiki`, `/d/platform`; as antigas `/chat` e `/cockpit` redirecionam) é dirigida por **um registry**: `apps/frontend/lib/domains.ts` define o agent map (4 domínios; `kind: workflow | grounded | tool`), a nav, a rota genérica e os prompts sugeridos — **adicionar domínio = 1 entrada lá + um agente no backend**. No modo `shared`, os domínios montam globalmente mas são gated por tenant via **DomainAssignment** (ADR-010). `app/api/copilotkit/route.ts` registra um `CopilotRuntime` com um `HttpAgent` por domínio. A página usa `useCoAgentStateRender` para mostrar os passos intermediários, `useCopilotAction` (`renderAndWaitForResponse`) para o approval card, e um `EvidencePanel` para as fontes citadas + badges de assurance.
- **Backend** → `app/main.py` cria o FastAPI (rodado como `app.main:app`) e expõe o endpoint AG-UI `/helpdesk` para o workflow `triage → retrieve → resolve → (condicional) escalate` embrulhado como **workflow-as-agent** (mais `/cockpit`, `/selfwiki`, e o tool-driven `/platform` + seu gêmeo `/platform-hosted`). Camadas: `app/api` (routers finos) → `app/services` → `app/workflow` / `app/agents` / `app/core`. A resolução de tenant (modo `shared`) + brokering de credenciais ficam no `app/core` (seam `TenantConfigProvider`).
- **Foundry** → o retriever consulta a **Foundry IQ KB** e trima por entitlement (`app/agents/secure_search.py`, `app/knowledge/acl_setup.py`); triage/resolver leem/escrevem **memória**; eval e traces vão para o Foundry Control Plane.

**O ponto de maior risco — de-riscar primeiro (Fase 2):** expor um **workflow multi-agente** (não um agente único) sobre AG-UI de forma que o frontend receba os **passos intermediários** (triage, retrieval, draft), não só a resposta final. O caminho é *workflow-as-agent*. Valide que os passos chegam ao UI antes de investir no resto.

Estrutura-alvo do repo (ver seção 5 da spec): `backend/app/{agents,workflow,memory,knowledge,tools,server.py,settings.py}`, `apps/backend/eval/{datasets,rubrics,assert,run_eval.py}`, `frontend/app/{api/copilotkit,components}`, `infra/` (bicep/azd).

## Regras inegociáveis

1. **NÃO invente assinaturas de SDK.** A superfície dos SDKs muda rápido — em especial o namespace `.beta` de `azure-ai-projects`. Antes de fixar qualquer chamada a `azure-ai-projects`, `agent-framework` ou `agent-framework-ag-ui`, verifique contra `learn.microsoft.com/azure/foundry` e o repo `microsoft-foundry/foundry-samples`. Se não conseguir confirmar, deixe um `# TODO: verificar assinatura` explícito em vez de chutar. Os trechos de código na spec são **esqueleto/forma**, não copy-paste final.
2. Auth **sempre** via `DefaultAzureCredential`. Nada de API key hardcoded.
3. Cada fase tem sinal **verde/vermelho** (ver abaixo). **Não avança** sem o verde da fase atual.
4. Toda resposta do resolver **DEVE** conter ao menos uma citação de fonte. É policy de eval (ASSERT pega violação).
5. A tool `create_ticket` só pode disparar **após aprovação humana explícita** — e a aprovação HITL exige o papel **Approver** (ou **Admin**). Autorização vem de App Roles do Entra (Admin / Author / Approver / Reader) no claim `roles` do token; gestão de usuários + papéis fica em `/admin/users` (via Microsoft Graph, app-only). Plano: [`docs/RBAC-AND-USER-MANAGEMENT-PLAN.md`](./docs/RBAC-AND-USER-MANAGEMENT-PLAN.md).
6. **Controle de acesso é DADO** (os grupos de leitura de cada fonte), **nunca lógica de classificação no código**. O acesso segue a fonte: grupos vêm do manifesto/`COCKPIT_ACL_CLASSIFICATION`, nomes resolvem para object-IDs via `COCKPIT_ACL_GROUP_MAP`; doc sem acesso declarado → fail-closed. Ver [`docs/METHOD.md`](./docs/METHOD.md).

## Ordem de implementação (fases)

Cada fase é independente e testável. Não avança sem o verde.

- **Fase 0** — Esqueleto + hello-world sobre AG-UI. Provisiona o Foundry project (`azd`), sobe agente trivial no FastAPI com AG-UI, conecta CopilotKit. 🟢 mensagem faz round-trip com streaming visível no chat. 🔴 CORS bloqueando ou `DefaultAzureCredential` falhando local.
- **Fase 1** — Base de conhecimento (Foundry IQ). Ingesta ~10-20 markdowns de runbook fake; retriever responde citando fonte. 🟢 cita doc real; pergunta fora do corpus → "não sei". 🔴 retrieval vazio ou resposta sem citação.
- **Fase 2** *(maior risco)* — Workflow + streaming dos passos. `WorkflowBuilder`: triage → retrieve → resolve, embrulhado como workflow-as-agent via AG-UI; frontend renderiza os passos. 🟢 os 3 passos aparecem conforme executam. 🔴 UI só vê a saída final.
- **Fase 3** — Memória. Liga user + procedural + session. Lê preferências antes de responder; escreve a resolução depois. 🟢 2ª sessão recupera o stack sem reperguntar. 🔴 memória write-only (grava mas nunca lê de volta).
- **Fase 4** — Human-in-the-loop + tool. Edge condicional: groundedness baixa OU ação → `ApprovalCard` → `create_ticket`. 🟢 aprovar → ticket criado e renderizado; rejeitar → volta pro loop. 🔴 tool dispara sem passar pela aprovação.
- **Fase 5** — Eval. Harness offline (groundedness + Rubric no golden set); ASSERT com policies no CI; traces no Foundry. 🟢 scores ligados aos traces; ASSERT pega violação plantada. 🔴 evals rodam mas não bloqueiam nada (sem gate).
- **Fase 6** *(opcional)* — Deploy. Empacota o workflow como hosted agent no Foundry Agent Service.

## Comandos

> Rodam a partir das pastas indicadas (estrutura já existe). Ver [`README.md`](./README.md) para o runbook completo.

- Backend (de `apps/backend/`): `uv run uvicorn app.main:app --port 8000 --reload`
- Frontend (de `apps/frontend/`): `npm run dev` (porta 3000)
- Eval (de `apps/backend/`): `uv run python eval/run_eval.py`
- Provisioning: `azd up`

## Referências

- Foundry samples: `github.com/microsoft-foundry/foundry-samples` (pasta `python/hosted-agents/agent-framework`)
- Build 2026 demos (memory, toolboxes, eval): `github.com/microsoft-foundry/build-2026-demos`
- Agent Framework: `github.com/microsoft/agent-framework`
- AG-UI ↔ Agent Framework: `learn.microsoft.com/agent-framework/integrations/ag-ui/`
- CopilotKit + MAF: `docs.copilotkit.ai/ms-agent-dotnet` (vale p/ Python também)
- Foundry IQ cookbook: `microsoft-foundry/forgebook` → notebook "mastering-foundry-iq"
- ASSERT (eval policies): `aka.ms/assert`
