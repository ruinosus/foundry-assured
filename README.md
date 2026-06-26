# Foundry Helpdesk

An internal engineering support **concierge** — a Microsoft Foundry showcase that
exercises every Foundry pillar hands-on: a grounded knowledge base, a streamed
multi-agent workflow, per-user memory, human-in-the-loop approval, offline
evaluation, and a managed hosted-agent deployment. The frontend is **CopilotKit**
(Next.js) talking to a Python backend over the **AG-UI** protocol.

> **Clone → provision → deploy:** [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md) — the
> step-by-step runbook (infra, Entra app registrations, KB/memory, hosted agent,
> Container Apps).
> **Make it your own domain:** [`docs/CUSTOMIZE.md`](./docs/CUSTOMIZE.md) — swap the
> corpus, prompts, action and identity to turn this into any "ask → ground → resolve →
> escalate" assistant.
> **Case study:** [`docs/CASE-STUDY-LLM-WIKI-LOOP.md`](./docs/CASE-STUDY-LLM-WIKI-LOOP.md) —
> a measured generate→verify→ingest→consume loop for grounding an agent on a large codebase.
> Contributing & CI/CD: [`CONTRIBUTING.md`](./CONTRIBUTING.md) · security:
> [`SECURITY.md`](./SECURITY.md) · full build spec:
> [`foundry-helpdesk-spec.md`](./foundry-helpdesk-spec.md) · working rules:
> [`CLAUDE.md`](./CLAUDE.md)

A developer asks in chat → the system **triages** intent/urgency → **retrieves**
from the runbook knowledge base → **resolves** with a grounded, cited answer →
**escalates** with human approval when an action is needed → and the whole thing
is **evaluated** and **traceable**.

## Quickstart

```bash
azd auth login && az login
azd up                      # provision Azure infra
./scripts/setup-entra.sh    # optional: Entra sign-in + OBO (skip to run without auth)
./scripts/bootstrap.sh      # fill .env, ingest the knowledge base, provision memory

cd apps/backend  && uv run uvicorn app.main:app --port 8000 --reload
cd apps/frontend && npm install && npm run dev      # http://localhost:3000
```

Full runbook + the manual steps behind the scripts: [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md).
Adapt it to your own domain: [`docs/CUSTOMIZE.md`](./docs/CUSTOMIZE.md).

## Demo mode — see it with **no Azure**

Want to see the experience before provisioning anything? Committed AG-UI fixtures are
replayed by [CopilotKit **aimock**](https://github.com/CopilotKit/aimock) — the real
frontend renders the real flow (triage→retrieve→resolve **steps**, grounded **cited**
answers, honest off-corpus decline) with **no Azure and no Python backend**:

```bash
cd apps/frontend && npm install && npm run demo      # → http://localhost:3000
```

The fixtures are **recorded from real runs** (`./scripts/demo-record.sh`), so they're
genuine workflow output, not hand-faked — just replayed deterministically. Try the
recorded prompts: *"How do I roll back a bad deploy?"*, *"My Kubernetes pod is stuck in
CrashLoopBackOff…"*, *"What's the weather in Paris?"* (off-corpus → declines).

> The **HITL ticket approval** isn't in the fixture yet (the resume handshake is
> captured by recording through the live UI); it runs in the full app. Add it by
> re-recording with `./scripts/demo-record.sh` and approving a ticket in the browser.

## Status — all six phases green

| Phase | Pillar | What it proves |
| --- | --- | --- |
| 0 | AG-UI hello-world | message round-trips with streaming |
| 1 | Foundry IQ knowledge base | answers cite a runbook, decline off-corpus |
| 2 | Multi-agent workflow | `triage → retrieve → resolve` steps stream to the UI |
| 3 | Memory + **Entra ID / OBO** | per-user memory, Foundry called *as the signed-in user* |
| 4 | Human-in-the-loop | ticket escalation pauses for explicit approval before `create_ticket` |
| 5 | Evaluation | deterministic policy gate + Foundry judges, surfaced on `/evals` from the project; CI runs Microsoft's official [`ai-agent-evals`](https://github.com/microsoft/ai-agent-evals) action on the deployed agent |
| 6 | Hosted-agent deploy | same workflow packaged as a managed Foundry hosted agent |

## Architecture

Three layers. The Next.js frontend talks to the Python backend over **AG-UI (SSE)**;
the backend runs a **multi-agent workflow** against Foundry in the cloud. Phase 6
adds a second, parallel delivery model: the same workflow packaged as a **managed
hosted agent** (Responses protocol) on Foundry Agent Service.

```
                         ┌─────────────────── Foundry (cloud) ───────────────────┐
 Browser                 │  gpt-4.1-mini · Foundry IQ KB (Azure AI Search)         │
   │  CopilotKit         │  memory store · evaluation · App Insights (OTEL)        │
   ▼                     └─────────▲───────────────────────────▲──────────────────┘
 Next.js ── /api/copilotkit ──► Backend (FastAPI, AG-UI)        │ Responses
   │   helpdesk  (AG-UI)        triage→retrieve→resolve→escalate │ (managed)
   │                           OBO · memory · HITL approval      │
   └── helpdesk-hosted ──► Backend /helpdesk-hosted (bridge) ──► Hosted agent (Agent Service)
                           Responses → AG-UI                     triage→retrieve→resolve
```

**Two ways to consume the same agent** (switchable in the UI):

- **Live workflow (AG-UI)** — the rich experience: intermediate workflow steps
  stream into the chat, the approval card gates ticket creation, and Foundry is
  called *on-behalf-of* the signed-in developer (OBO) with per-user memory.
- **Hosted agent (Foundry)** — the same `triage → retrieve → resolve` workflow,
  deployed as a managed, autoscaling agent you invoke by name over the Responses
  API. Request→response (no live steps/HITL — those are inherent to AG-UI), runs
  under its own platform identity, and costs nothing while idle.

## Repository layout

A monorepo: deployable apps live under `apps/`; infra and docs sit alongside.
Each app is internally layered (backend: thin routers → services → core;
frontend: feature-organized components).

```
apps/
  backend/                    Python 3.12 · FastAPI · Agent Framework · uv
    app/
      main.py                 app wiring: CORS, lifespan, routers, AG-UI /helpdesk
      core/                   settings.py · auth.py (Entra JWT + OnBehalfOf / OBO)
      api/                    thin HTTP routers: health · chat (/helpdesk-hosted) · tickets · evals
      services/               hosted.py — Responses→AG-UI bridge for the hosted agent
      agents/                 prompts.py (single source of truth) · concierge.py
      workflow/               graph · agents · escalation · memory · stream_fix (multi-agent)
      tools/tickets.py        real create_ticket tool + persistence
      knowledge/              corpus/*.md (~13 runbooks) · ingest.py
    cli/                      data-plane scripts: provision_memory · provision_guardrail · provision_eval_rule
    eval/                     Phase 5 — offline harness (run_eval · assertions · datasets · rubrics)
  frontend/                   Next.js 15 (App Router) · CopilotKit v2 · MSAL
    app/                      routes only: page (Overview) · chat · tickets · evals · api/* proxies
    components/{shell,chat,evals,tickets}/   feature-organized (HelpdeskApp, AppShell, …)
    lib/auth/msal.ts · styles/globals.css
  hosted-agent/               Phase 6 — hosted-agent container (main · Dockerfile · agent.yaml)
infra/                        Bicep (azd): Foundry + AI Search + Storage + ACR + Container Apps + RBAC
scripts/set-deploy-env.sh     copies Entra values from .env into the azd env (for publishing)
docs/                         DEPLOYMENT.md (provisioning runbook) · presentation.html (slide deck)
azure.yaml                    azd config — services point at apps/{backend,frontend,hosted-agent}
.github/workflows/eval-gate.yml   CI: the policy gate self-test
```

## Run locally

### 1. Provision Foundry (azd)

```bash
azd auth login
azd up        # prompts for env name + location; provisions everything in infra/
```

Creates `rg-<env>`, the Foundry account + project **`helpdesk-concierge`**, a
`gpt-4.1-mini` + `text-embedding-3-small` deployment, **Azure AI Search (Basic)**,
Storage, an **ACR** (for the Phase 6 image), and keyless RBAC. Pick a region where
`gpt-4.1-mini` GlobalStandard is available; AI Search may need a different region
(set `AZURE_SEARCH_LOCATION`).

### 2. Backend + data-plane objects

```bash
cd apps/backend
cp .env.example .env                       # fill from `azd env get-values`
az login
uv run python -m app.knowledge.ingest      # build the Foundry IQ knowledge base
uv run python -m cli.provision_memory      # create the memory store
uv run uvicorn app.main:app --port 8000 --reload
```

Knowledge base and memory store are **data-plane** objects created by scripts (not
Bicep) — Bicep is control-plane only. Auth is always `DefaultAzureCredential`.

### 3. Frontend

```bash
cd apps/frontend
cp .env.example .env.local                 # NEXT_PUBLIC_ENTRA_* for Entra sign-in
npm install
npm run dev                                # http://localhost:3000
```

- **`/`** — Overview (hero + the six capability cards).
- **`/chat`** — the concierge. Toggle **Live workflow** (AG-UI: steps, approval,
  OBO, memory) ⇄ **Hosted agent** (the deployed Foundry agent).
- **`/evals`** — recorded eval runs with direct links to the Foundry portal report.

### Entra ID (OBO) sign-in

When `NEXT_PUBLIC_ENTRA_*` are set, the chat gates behind Microsoft sign-in and
forwards the user's token; the backend does the On-Behalf-Of exchange and calls
Foundry/KB/memory **as the user**. Two app registrations: a SPA (`redirect
http://localhost:3000`) and an API (`scope access_as_user`, `requestedAccessToken
Version: 2`). Unset → falls back to `DefaultAzureCredential` so it still boots.

## Evaluation (Phase 5)

```bash
cd apps/backend
uv run python -m eval.run_eval              # local policy gate over real agent outputs
uv run python -m eval.run_eval --cloud      # + Foundry groundedness/relevance/coherence (portal link)
uv run python -m eval.run_eval --self-test  # prove the gate catches a planted violation (offline)
```

The **LocalEvaluator** policies (every answer cites a runbook or declines; never
leak a secret) are the hard CI gate — a violation exits non-zero. **FoundryEvals**
adds cloud LLM-judge scores, viewable per-run in the Foundry portal. CI runs the
offline `--self-test` (`.github/workflows/eval-gate.yml`). See
[`apps/backend/eval/README.md`](./backend/eval/README.md).

## Hosted agent (Phase 6)

The workflow packaged as a managed Foundry hosted agent (Responses protocol),
deployed via the Azure-recommended `azd ai agent` path:

```bash
# one-time: the azure.yaml already declares the helpdesk-concierge agent service
azd env set AZURE_AI_PROJECT_ID "<project ARM id .../projects/helpdesk-concierge>"
azd deploy helpdesk-concierge               # remote build → ACR → create agent version → active
azd ai agent show helpdesk-concierge        # status + endpoint + portal playground
azd ai agent invoke helpdesk-concierge "How do I roll back a bad deploy?"
```

> **Post-deploy RBAC** (the agent gets its own identity at deploy time, so it
> can't be pre-assigned in Bicep): grant the agent's *Instance Identity Principal
> ID* (from `azd ai agent show`) **Azure AI User** on the account and **Search
> Index Data Reader** on the search service, or it returns 403 at runtime.

## Safety & continuous evaluation (Foundry add-ons)

Beyond the offline harness, two data-plane scripts wire up Foundry's safety and
online-eval surfaces on the deployed agent (run after `azd deploy`):

```bash
# Adversarial / jailbreak eval (offline): refuse-or-ground gate + Foundry safety judges
uv run python -m eval.run_eval --safety [--cloud]

# Content Safety guardrail: screen every prompt + response at runtime (default RAI policy)
uv run python -m cli.provision_guardrail

# Continuous (online) evaluation: score the agent's LIVE responses against an eval
uv run python -m cli.provision_eval_rule --eval-id eval_xxx     # eval_xxx from a --cloud run's portal URL
```

The `--safety` run shows many jailbreaks are stopped by Azure's content + jailbreak
filter *before* the model (🛡️). `guardrail_provision` adds an agent-level RAI
guardrail; `eval_rule_provision` registers a rule that scores every `RESPONSE_COMPLETED`
and links the score to its trace in the Foundry Control Plane.

## Publish backend + frontend (Azure Container Apps)

Both apps ship as containers to Azure Container Apps, built/pushed by azd. The
infra (`infra/containerapps.bicep`) adds a Container Apps environment + Log
Analytics + the two apps, all running as a shared managed identity (ACR pull, and
— for the backend — Foundry + search access). The apps find each other by FQDN,
so no manual URL wiring.

```bash
# 1. Browser-baked values (NEXT_PUBLIC_* are compiled into the bundle at image
#    build) + the backend OBO secret — set them in the azd env first:
azd env set NEXT_PUBLIC_ENTRA_TENANT_ID    <tenant-id>
azd env set NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID <spa-client-id>
azd env set NEXT_PUBLIC_ENTRA_API_CLIENT_ID <api-client-id>
azd env set ENTRA_TENANT_ID                 <tenant-id>
azd env set ENTRA_API_CLIENT_ID             <api-client-id>
azd env set ENTRA_API_CLIENT_SECRET         <api-secret>     # → container app secret

# 2. Provision the Container Apps + build/push/deploy both images:
azd up                       # or: azd provision && azd deploy backend && azd deploy web

# 3. Register the web app's URL as an Entra SPA redirect URI (one-time):
azd env get-values | grep WEB_URL
#    add  https://<web-fqdn>/  to the SPA app registration → Authentication → redirect URIs
```

The backend's `FRONTEND_ORIGIN` (CORS) and the web's `AGUI_URL` / `HOSTED_AGUI_URL`
/ `BACKEND_URL` are wired to each other's FQDN by Bicep. Images build remotely in
ACR (`remoteBuild: true`), so no local Docker/amd64 step is needed.

## Cost & teardown

| Resource | Cost | Note |
| --- | --- | --- |
| Azure AI Search (Basic) | ~$0.10/hr | billed while it exists |
| ACR (Basic) | ~$5/mo | holds the hosted-agent image |
| Hosted agent compute | **$0 idle** | deprovisions after 15 min inactivity |
| Models | per-token | |

```bash
azd ai agent delete helpdesk-concierge   # remove just the hosted agent
azd down --purge                         # delete the whole resource group (stops AI Search)
```

## References

- Agent Framework evaluation — learn.microsoft.com/agent-framework/agents/evaluation
- Deploy a hosted agent — learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent
- agent-framework hosting samples — github.com/microsoft/agent-framework `python/samples/04-hosting/foundry-hosted-agents`
- AG-UI ↔ Agent Framework — learn.microsoft.com/agent-framework/integrations/ag-ui/
