# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Estado atual

Repositório **greenfield**: por enquanto só existe `foundry-helpdesk-spec.md` (o build spec completo). Nenhum código foi escrito ainda. A spec é a fonte de verdade para arquitetura, stack e ordem de implementação — leia-a antes de começar qualquer fase.

## O que é

Showcase do **Microsoft Foundry** — um concierge de suporte de engenharia interno. Dev pergunta no chat → sistema **tria** intenção/urgência → **busca** na base de conhecimento → **redige** resposta fundamentada com citações → **decide** se basta responder ou se precisa de ação (abrir ticket/escalar) com **aprovação humana** → **lembra** preferências e resoluções entre sessões. Tudo **avaliado** (groundedness + rubric + policies) e **rastreável** (OpenTelemetry).

O domínio é **swappable**: a arquitetura "pergunte → fundamente → resolva → escale" vale para qualquer assistente do tipo. Trocar o domínio = trocar o corpus de conhecimento e os prompts.

## Stack

- **Backend** (Python 3.12): `agent-framework` (agentes + `WorkflowBuilder`), `agent-framework-ag-ui` (adapter AG-UI: `AgentFrameworkAgent`, `add_agent_framework_fastapi_endpoint`), `azure-ai-projects>=2.2.0` (Foundry client: KB, `.beta.memory_stores`, eval), `azure-identity` (`DefaultAzureCredential`), `fastapi`, `uvicorn`. Deps via **`uv`**.
- **Frontend** (Next.js 15, App Router): `@copilotkit/react-core`, `@copilotkit/react-ui`, `@copilotkit/runtime`, com `HttpAgent` apontando para o endpoint AG-UI do backend.
- **Foundry** (provisionar via `azd` + extensão Foundry): project + model deployment (default seguro: **`gpt-4.1-mini`**), Foundry IQ knowledge base, memory store, Application Insights (tracing OTEL).

## Arquitetura (big picture)

Três camadas. O frontend Next.js conversa com o backend Python via **AG-UI sobre SSE**; o backend roda um **workflow multi-agente** que usa o Foundry na nuvem.

- **Frontend** → `app/api/copilotkit/route.ts` registra um `CopilotRuntime` com um `HttpAgent` para `http://localhost:8000/helpdesk`. A página usa `useCoAgentStateRender` para mostrar os passos intermediários e `useCopilotAction` (`renderAndWaitForResponse`) para o approval card.
- **Backend** → `app/server.py` cria o FastAPI e chama `add_agent_framework_fastapi_endpoint(app, agent=build_helpdesk_agent(), path="/helpdesk")`. O `build_helpdesk_agent()` em `app/workflow/graph.py` monta o grafo `triage → retrieve → resolve → (condicional) escalate` com `WorkflowBuilder` e o embrulha como **workflow-as-agent** (`wf.as_agent(...)`) para falar AG-UI.
- **Foundry** → o retriever consulta a **Foundry IQ KB** (`app/knowledge/kb.py`); triage/resolver leem/escrevem **memória** (`app/memory/store.py`, escopos user/procedural/session); eval e traces vão para o Foundry Control Plane.

**O ponto de maior risco — de-riscar primeiro (Fase 2):** expor um **workflow multi-agente** (não um agente único) sobre AG-UI de forma que o frontend receba os **passos intermediários** (triage, retrieval, draft), não só a resposta final. O caminho é *workflow-as-agent*. Valide que os passos chegam ao UI antes de investir no resto.

Estrutura-alvo do repo (ver seção 5 da spec): `backend/app/{agents,workflow,memory,knowledge,tools,server.py,settings.py}`, `apps/backend/eval/{datasets,rubrics,assert,run_eval.py}`, `frontend/app/{api/copilotkit,components}`, `infra/` (bicep/azd).

## Regras inegociáveis

1. **NÃO invente assinaturas de SDK.** A superfície dos SDKs muda rápido — em especial o namespace `.beta` de `azure-ai-projects`. Antes de fixar qualquer chamada a `azure-ai-projects`, `agent-framework` ou `agent-framework-ag-ui`, verifique contra `learn.microsoft.com/azure/foundry` e o repo `microsoft-foundry/foundry-samples`. Se não conseguir confirmar, deixe um `# TODO: verificar assinatura` explícito em vez de chutar. Os trechos de código na spec são **esqueleto/forma**, não copy-paste final.
2. Auth **sempre** via `DefaultAzureCredential`. Nada de API key hardcoded.
3. Cada fase tem sinal **verde/vermelho** (ver abaixo). **Não avança** sem o verde da fase atual.
4. Toda resposta do resolver **DEVE** conter ao menos uma citação de fonte. É policy de eval (ASSERT pega violação).
5. A tool `create_ticket` só pode disparar **após aprovação humana explícita**.

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

> Aspiracionais — a estrutura ainda não existe. Rodam a partir das pastas indicadas depois do scaffold.

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
