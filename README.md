# Foundry Assured

**An internal engineering support assistant that proves what it tells you.**

Ask it a question and it answers from your own runbooks, showing the source of every
claim. If the answer requires *doing* something — opening a ticket, changing a
resource — it stops and asks a human first. It never invents a source, never shows
you a document you are not entitled to read, and never writes anything without
approval. Those are not promises in a README: each one is a test that fails the
build when broken.

Built as a **Microsoft Foundry** showcase — knowledge base, multi-agent workflow,
per-user memory, human-in-the-loop approval, evaluation and tracing — with an
assurance layer on top. Frontend is **CopilotKit** (Next.js) over the **AG-UI**
protocol; backend is Python.

---

## What you actually get

Sign in with your Microsoft account and you land in a console with four assistants.

| Screen | What it is |
|---|---|
| `/d/helpdesk` | The support concierge — the full triage → retrieve → resolve → escalate workflow |
| `/d/cockpit` | Cited Q&A over the Cockpit documentation |
| `/d/selfwiki` | Cited Q&A over a wiki generated from **this repository's own code** |
| `/d/platform` | Ops concierge over Microsoft MCP servers — Azure, GitHub, Entra, ADO, Learn |
| `/tickets` | The tickets that were actually opened |
| `/evals` | Quality scores for the agent's answers |
| `/admin/users` | Users and role assignments (via Microsoft Graph) |

### What happens when you ask something

Type *"how do I recover my GitHub 2FA?"* into the helpdesk and you watch it work:

1. **Triage** — classifies intent and urgency.
2. **Retrieve** — searches the knowledge base, trimmed to what *you* are allowed to see.
3. **Resolve** — answers with at least one citation. The **evidence panel** beside the
   chat shows where each claim came from. No source, no answer — it declines instead of
   guessing.
4. **Escalate** — if action is needed, an **approval card** appears. The ticket is
   created only after you approve it, and only if you hold the **Approver** role.
5. **Remember** — preferences and resolutions carry across sessions.

The intermediate steps stream to the screen as they happen. You are not staring at a
spinner waiting for a paragraph.

The `platform` domain works differently: it does not search documents, it **calls
tools**. Read operations answer directly; every **write** goes behind human approval
with a required role per tool.

---

## Why "Assured"

Anyone can wire a chatbot to a vector store. The hard part is being able to say what it
will and will not do — and prove it. Every guarantee below is enforced by something that
turns CI red:

| Guarantee | How it is proved |
|---|---|
| Every answer cites a source | Policy gate that **plants a violation** and fails if it is not caught |
| You only see what you may see | Per-document ACL applied **before** the model sees the content |
| No write without a human | Approval **plus** the Approver role, structurally — the ticket is created only in the response handler |
| The wiki does not lie about the code | Build-fidelity floor at 80% (currently **96.4%**) + a freshness gate |
| The architecture does not rot | 14 module-boundary contracts checked by `import-linter` on every push |
| Prompts cannot drift silently | Prompt-contract suite over the declarative agent definitions |

Read the method in [`docs/METHOD.md`](./docs/METHOD.md).

---

## The domain is swappable

The architecture is *"ask → ground → resolve → escalate"*. Swapping the domain means
swapping the corpus and the prompts — the machinery does not change. The shipped corpus
is 13 generic engineering runbooks (2FA recovery, deploy rollback, pod crashloop, prod
credential rotation, incident severity…), which is enough to see it work and not enough
to be useful to your team. Making it yours: [`docs/CUSTOMIZE.md`](./docs/CUSTOMIZE.md).

---

## Deployment modes — multi-tenant SaaS

On top of the showcase + assurance mechanism, the repo has evolved into a **hybrid
multi-tenant SaaS** — one codebase, three deployment modes, selected by a
**deployment-mode seam** ([ADR-007](./docs/adr/ADR-007-coexistence-deployment-mode.md)).
A `TenantConfigProvider` (Single/Multi impl) is the single point of variation; everything
else is identical across modes. All data, compute, and credentials stay in the customer's
cloud (BYO) — the control plane stores **per-tenant config + connection references only,
never secrets, never customer data** ([ADR-005](./docs/adr/ADR-005-never-store-secrets.md)).

| Mode | Tenancy | Where | Vehicle |
| --- | --- | --- | --- |
| **self_hosted** (today, default) | 1 | customer cloud, customer operates | `azd up` (byte-identical to before) |
| **dedicated** (enterprise) | 1 | customer cloud, we operate | Azure **Managed Application** + **Lighthouse** |
| **shared** (SMB/default SaaS) | N | our cloud | multi-tenant control plane; tenant resolved per-request from the Entra `tid` |

In **shared** mode each request resolves its tenant from the token's `tid`, loads that
tenant's config + `Connection` records, mints a brokered token (OBO for Microsoft-audience
servers; OAuth identity passthrough / Foundry connections otherwise — **we never read a
secret**), and calls the customer's own data plane. Memory is namespaced by tenant. The
**dedicated** stamp is deployed into the customer's own subscription as an Azure **Managed
Application** ([`infra/managed-app/`](./infra/managed-app)) with cross-tenant management via
Azure **Lighthouse** ([`infra/lighthouse/`](./infra/lighthouse), [ADR-002](./docs/adr/ADR-002-dedicated-stamp-managed-app-lighthouse.md)).

> Target architecture: [`docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md`](./docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md) ·
> tenancy model: [ADR-001](./docs/adr/ADR-001-tenancy-deployment-stamps.md) ·
> the full ADR index (001–011): [`docs/adr/README.md`](./docs/adr/README.md) ·
> packaging the dedicated stamp + hosted platform agent: [`docs/D-PACKAGING-RUNBOOK.md`](./docs/D-PACKAGING-RUNBOOK.md).

The single-tenant `self_hosted` mode below is the **default**, byte-identical to the
pre-SaaS product — everything in this README runs unchanged in that mode unless a section
says otherwise.

## How the four domains are wired

The frontend is an **Assurance Console** that fronts four agents. Three are
**grounded/workflow** domains sharing the same grounded/assured plumbing; the fourth is
a **tool-driven** ops concierge:

- **helpdesk** — the multi-agent workflow above (triage → retrieve → resolve →
  escalate, with HITL).
- **cockpit** — grounded, cited Q&A over the `cockpit-kb` corpus.
- **selfwiki** — grounded, cited Q&A over a deep-wiki generated from **this repo's
  own source** (the dogfood).
- **platform** — a **tool-driven** ops concierge over Microsoft first-party MCP servers
  (Learn, Azure, Entra, Azure DevOps, GitHub), with **HITL approval on write actions**.
  Unlike the three grounded domains it resolves answers by *calling tools*, not by
  retrieving a corpus; it also has the **live-vs-hosted toggle** (its hosted twin is the
  deployed **platform** agent — see [Deployment modes](#deployment-modes--multi-tenant-saas)).

Domains are **config-driven**: a single registry, [`apps/frontend/lib/domains.ts`](./apps/frontend/lib/domains.ts),
drives the agent map, the nav, the generic console route, and the per-domain
suggested prompts. Adding a domain = **one entry there + a backend agent**; deploy
any subset (cockpit and selfwiki only register once their KB is ingested). In **shared**
mode, domains mount globally but are gated per-tenant by a **license entitlement**
(`DomainAssignment`, [ADR-010](./docs/adr/ADR-010-per-tenant-domain-entitlement.md)).

### Two wiki-generation paths

The deep-wiki the **selfwiki** domain grounds on can be generated two ways:

- **Foundry pipeline** — [`apps/backend/app/modules/knowledge/internal/wiki_builder.py`](./apps/backend/app/modules/knowledge/internal/wiki_builder.py),
  automated via `uv run`, using the Foundry model (`gpt-5-mini`) with the build-fidelity
  gate. Costs roughly **$0.30** for the whole monorepo.
- **Microsoft Agent Skills** — [`apps/backend/app/modules/knowledge/skills/{wiki-architect,wiki-page-writer}`](./apps/backend/app/modules/knowledge/skills).
  Open the repo in **VS Code Copilot or Claude Code** and ask it to *"create a wiki"*;
  the IDE agent reads the `SKILL.md` and runs the loop. **No cloud, no azd, no cost** —
  it uses the IDE's own Copilot.

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

## What is built

Every row below is shipped and exercised, not planned.

| Capability | What it means in the running app |
| --- | --- |
| Grounded knowledge base | answers cite a runbook and **decline** when the question is off-corpus |
| Multi-agent workflow | `triage → retrieve → resolve` streams its steps to the UI as they run |
| Memory + Entra ID / OBO | per-user memory; Foundry is called **as the signed-in user**, not as the app |
| Human-in-the-loop | escalation pauses for explicit approval before `create_ticket` ever runs |
| Evaluation | deterministic policy gate + Foundry judges, surfaced on `/evals`; CI runs Microsoft's [`ai-agent-evals`](https://github.com/microsoft/ai-agent-evals) against the deployed agent |
| Hosted agents | the same workflow packaged as a managed Foundry hosted agent |
| Multi-tenant SaaS | one codebase, three deployment modes — see below |
| Modular monolith | ten domain modules with boundaries enforced in CI ([ADR-017](./docs/adr/ADR-017-module-boundaries.md)) |

## Assurance mechanism

The repo's headline differentiator: a domain-agnostic recipe to point an agent at one or
more repos/knowledge bases and get **measured, gated** guarantees — the company brings the
data, the mechanism brings the guarantees. Each pillar is a number wired to a CI gate
(thresholds in [`apps/backend/eval/assurance.yaml`](./apps/backend/eval/assurance.yaml)):

| Pillar | Guarantee | Gate |
| --- | --- | --- |
| **Build** | every wiki claim cites a real source file | fidelity gate (`wiki_builder`) |
| **Recall** | nothing relevant is left out of retrieval | recall measured (agentic effort) |
| **Completeness** | answers are grounded *and* complete | completeness gate (`run_eval`) |
| **Access control** | each caller sees only their entitlement — access **follows the source** (no classification in code); enforced pre-model, defense-in-depth (service-side passthrough + app-side trim) | access-control gate (`access_control_test`, violations = 0) |
| **Red-team** | no prompt leaks content across groups | red-team gate (`red_team_test`, ASR ≤ ceiling) |

Full as-built model: [`docs/METHOD.md`](./docs/METHOD.md) · visual walkthrough:
[`docs/use-case-demo.html`](./docs/use-case-demo.html) · design rationale:
[`docs/ASSURANCE-MECHANISM-PLAN.md`](./docs/ASSURANCE-MECHANISM-PLAN.md).

## Architecture

Three layers. The Next.js frontend talks to the Python backend over **AG-UI (SSE)**;
the backend runs a **multi-agent workflow** against Foundry in the cloud. The hosted-agent path
adds a second, parallel delivery model: the same workflow packaged as a **managed
hosted agent** (Responses protocol) on Foundry Agent Service.

The diagram below shows the **self_hosted** (single-tenant) topology. In **shared** mode
the same backend resolves the tenant per-request from the Entra `tid` and calls *that
tenant's* Foundry/KB/memory; see [Deployment modes](#deployment-modes--multi-tenant-saas).

The three layers — frontend, backend, and Foundry:

```mermaid
flowchart TB
  subgraph FE["Frontend · Next.js + CopilotKit"]
    UI["/d/[domain] Assurance Console (MSAL sign-in)<br/>helpdesk · cockpit · selfwiki"]
  end
  subgraph BE["Backend · FastAPI (AG-UI over SSE)"]
    WF["/helpdesk · multi-agent workflow"]
    CK["/cockpit, /selfwiki · grounded agents + secure_search trim"]
  end
  subgraph FDY["Microsoft Foundry"]
    KB["Foundry IQ KB · Azure AI Search"]
    MEM["Memory store"]
    OBS["Tracing · App Insights"]
  end
  UI -->|"AG-UI / SSE"| WF
  UI -->|"AG-UI / SSE"| CK
  WF --> KB
  CK -->|"agentic retrieval + per-caller trim"| KB
  WF --> MEM
  BE --> OBS
```

The helpdesk workflow itself — triage, retrieve, resolve, and a human-approved escalation:

```mermaid
flowchart LR
  Q["Developer question"] --> T["triage"]
  T --> R["retrieve (runbook KB)"]
  R --> RES{"resolve: answer or action?"}
  RES -->|"answer"| A["grounded answer + citation"]
  RES -->|"action / low groundedness"| E["escalate → ApprovalCard"]
  E -->|"approved"| TK["create_ticket"]
  E -->|"rejected"| R
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
The backend is a **modular monolith by business domain** (ADR-017): one module per
bounded context, each with a public surface and private internals, over a minimal
shared kernel — with the boundaries checked in CI by `import-linter`.

```
apps/
  backend/                    Python 3.12 · FastAPI · Agent Framework · uv
    app/
      main.py                 composition root: telemetry → tenancy → routers → domains
      registry.py             DomainSpec + mount_domains (dispatch by `kind`) + include_routers
      shared/                 SHARED KERNEL: settings · auth (Entra JWT + OBO) · telemetry/
                              imports no business module — enforced, not a convention
      modules/                one package per domain, each public.py + internal/
        tenancy/              deployment-mode seam · tenant resolution · connections · entitlement
        knowledge/            corpus · ingest · wiki builder · per-document ACL · retrieval
        helpdesk/             the workflow: triage → retrieve → resolve → escalate (HITL)
        grounded/             the cited-Q&A archetype (cockpit, selfwiki)
        platform_ops/         tool-driven ops concierge over Microsoft MCP servers
        agentdefs/            every declarative agent definition (loader + composition)
        admin/ tickets/ hosted/ evaluation/
    agents/helpdesk/          the agent DEFINITIONS — AgentSchema PromptAgent per agent (+ personas · guardrails · eval-cases)
    cli/                      data-plane scripts: provision_memory · provision_guardrail · provision_eval_rule
    eval/                     the assurance harness as PRODUCT (run_eval · assertions · datasets · rubrics + the 8 CI gates)
    tests/                    tests mirroring the modules, plus smoke/ and architecture/
    importlinter.toml         the 14 boundary contracts
  frontend/                   Next.js 15 (App Router) · CopilotKit v2 · MSAL
    app/                      routes only: page (Overview) · chat · tickets · evals · api/* proxies
    components/{shell,chat,evals,tickets}/   feature-organized (HelpdeskApp, AppShell, …)
    lib/auth/msal.ts · styles/globals.css
  hosted-agent/               hosted-agent container (main · Dockerfile · agent.yaml)
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
`gpt-5-mini` + `text-embedding-3-small` deployment, **Azure AI Search (Basic)**,
Storage, an **ACR** (for the hosted-agent image), and keyless RBAC. Pick a region where
`gpt-5-mini` GlobalStandard is available; AI Search may need a different region
(set `AZURE_SEARCH_LOCATION`).

### 2. Backend + data-plane objects

```bash
cd apps/backend
cp .env.example .env                       # fill from `azd env get-values`
az login
uv run python -m app.modules.knowledge.internal.ingest      # build the Foundry IQ knowledge base
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
- **`/d/[domain]`** — the generic Assurance Console (defaults to **`/d/helpdesk`**;
  also **`/d/cockpit`** and **`/d/selfwiki`**). An **EvidencePanel** shows the
  sources a grounded answer cited plus its assurance badges. For helpdesk, toggle
  **Live workflow** (AG-UI: steps, approval, OBO, memory) ⇄ **Hosted agent** (the
  deployed Foundry agent). Legacy **`/chat`** and **`/cockpit`** redirect to
  `/d/<id>`.
- **`/admin/users`** — in-portal user + role management (Admin role only; see below).
- **`/evals`** — recorded eval runs with direct links to the Foundry portal report.

### Entra ID (OBO) sign-in

When `NEXT_PUBLIC_ENTRA_*` are set, the chat gates behind Microsoft sign-in and
forwards the user's token; the backend does the On-Behalf-Of exchange and calls
Foundry/KB/memory **as the user**. Two app registrations: a SPA (`redirect
http://localhost:3000`) and an API (`scope access_as_user`, `requestedAccessToken
Version: 2`). Unset → falls back to `DefaultAzureCredential` so it still boots.

### App roles & user management

Authorization rides in the token's **`roles`** claim via four Entra **App Roles** —
**Admin · Author · Approver · Reader**. The HITL ticket approval requires the
**Approver** (or **Admin**) role, so a Reader can ask and ground but can't green-light
an action. The in-portal admin page **`/admin/users`** manages users and their role
assignments through **Microsoft Graph** (app-only), backed by the backend's `/admin/*`
endpoints. Design + setup: [`docs/RBAC-AND-USER-MANAGEMENT-PLAN.md`](./docs/RBAC-AND-USER-MANAGEMENT-PLAN.md).

## Evaluation

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
[`apps/backend/eval/README.md`](./apps/backend/eval/README.md).

## Hosted agents

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

## Documentation

| | |
|---|---|
| [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md) | clone → provision → deploy, step by step |
| [`docs/CUSTOMIZE.md`](./docs/CUSTOMIZE.md) | swap the corpus, prompts and action for your own domain |
| [`docs/METHOD.md`](./docs/METHOD.md) | the assurance mechanism — how each guarantee is measured |
| [`docs/OBSERVABILITY.md`](./docs/OBSERVABILITY.md) | what telemetry is emitted, and what is deliberately not |
| [`docs/adr/`](./docs/adr/) | 18 architecture decisions, with the measurements behind them |
| [`docs/USE-THIS-TEMPLATE.md`](./docs/USE-THIS-TEMPLATE.md) | fork it as a template, with your own infra and CI identities |
| [`docs/RELEASE-AUTOMATION.md`](./docs/RELEASE-AUTOMATION.md) | merge → release → gated deploy |
| [`docs/CASE-STUDY-LLM-WIKI-LOOP.md`](./docs/CASE-STUDY-LLM-WIKI-LOOP.md) | a measured generate→verify→ingest→consume loop over a large codebase |
| [`CONTRIBUTING.md`](./CONTRIBUTING.md) · [`SECURITY.md`](./SECURITY.md) · [`CLAUDE.md`](./CLAUDE.md) | how to work in this repo |

## References

- Agent Framework evaluation — learn.microsoft.com/agent-framework/agents/evaluation
- Deploy a hosted agent — learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent
- agent-framework hosting samples — github.com/microsoft/agent-framework `python/samples/04-hosting/foundry-hosted-agents`
- AG-UI ↔ Agent Framework — learn.microsoft.com/agent-framework/integrations/ag-ui/
