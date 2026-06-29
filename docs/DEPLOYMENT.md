---
title: Deployment & provisioning guide
description: End-to-end steps from a fresh clone to a provisioned, optionally cloud-published Foundry Assured.
type: how-to
audience: operator
status: stable
updated: 2026-06-27
---

# Deployment & provisioning guide

End-to-end: from a fresh `git clone` to a fully provisioned, optionally
cloud-published Foundry Assured. Read top to bottom the first time.

> Architecture & repo layout: [`../README.md`](../README.md). This doc is the
> operational runbook.

## Quickstart (the short path)

Two scripts collapse most of the manual steps below. From the repo root, after
`azd auth login && az login`:

```bash
azd up                      # provision all Azure infra (Step 1)
./scripts/setup-entra.sh    # OPTIONAL: create the 2 Entra app regs + write env (Step 3)
./scripts/bootstrap.sh      # fill .env from azd, ingest the KB, provision memory (Steps 2+4)

cd apps/backend  && uv run uvicorn app.main:app --port 8000 --reload   # Step 5
cd apps/frontend && npm install && npm run dev                        # → http://localhost:3000
```

Skip `setup-entra.sh` to run **without sign-in** (single `DefaultAzureCredential`
identity). The rest of this doc is the **reference** behind those scripts — read it
to understand or do any step by hand.

## What gets provisioned

| Layer | How | Where |
| --- | --- | --- |
| Foundry account + project + models, Azure AI Search, Storage, ACR, Container Apps env, RBAC | **Bicep** via `azd up` (control plane) | `infra/` |
| Knowledge base + memory store | **Python scripts** (data plane) — or `scripts/bootstrap.sh` | `apps/backend/{app/knowledge/ingest.py, cli/}` |
| Entra app registrations (SPA + API) for sign-in + OBO | `scripts/setup-entra.sh` (or manual — Step 3) | — |
| Hosted agent (Foundry Agent Service) | `azd deploy helpdesk-concierge` + post-deploy RBAC | `apps/hosted-agent/` |
| Backend + frontend (Container Apps) | `azd up` / `azd deploy backend web` | `apps/{backend,frontend}/` |

## Prerequisites

- An **Azure subscription**; on it you need rights to create resources and assign
  roles (Owner, or Contributor + User Access Administrator). Hosted agents need
  **Foundry Project Manager** at project scope.
- [`azd`](https://aka.ms/azd) ≥ 1.26 · [`az` CLI](https://aka.ms/azcli) ≥ 2.80 ·
  [`uv`](https://docs.astral.sh/uv/) · **Node 20+** · Docker (optional — image
  builds happen remotely in ACR).
- `az bicep` (auto-installed by `az`) if you want to compile-check infra.

```bash
azd auth login
az login
```

---

## Step 1 — Provision Azure infra (`azd up`)

```bash
azd up        # prompts for an environment name + region
```

This runs `infra/` and creates, in a `rg-<env>` resource group:
a Foundry account `aif-helpdesk-<token>` + project **`helpdesk-concierge`**,
`gpt-5-mini` + `text-embedding-3-small` deployments, **Azure AI Search (Basic)**,
a Storage account, an **ACR**, a **Container Apps environment**, a shared managed
identity, and all keyless role assignments.

Region tips: pick where `gpt-5-mini` GlobalStandard has quota (e.g. `eastus2`);
if Azure AI Search is out of capacity there, set `AZURE_SEARCH_LOCATION` (e.g.
`eastus`). Lower `modelCapacity` in `infra/resources.bicep` on quota errors.

Read the outputs you'll need next:

```bash
azd env get-values | grep -E 'FOUNDRY_|AZURE_SEARCH_|AZURE_STORAGE_|AZURE_CONTAINER_REGISTRY_'
```

---

## Step 2 — Backend `.env`

```bash
cd apps/backend
cp .env.example .env     # then paste the azd outputs into the matching keys
```

Fill `FOUNDRY_PROJECT_ENDPOINT`, `AZURE_SEARCH_ENDPOINT`, `AZURE_STORAGE_*`, etc.
from `azd env get-values`. Leave the `ENTRA_*` keys for Step 3 (auth is optional —
without them the app falls back to `DefaultAzureCredential` and skips OBO).

---

## Step 3 — Entra app registrations (sign-in + OBO)

> **Fast path:** `./scripts/setup-entra.sh` does everything in this step (idempotent)
> and writes the env files. The steps below are the reference / manual fallback if
> consent needs a portal click.

You create **two** app registrations: a **SPA** (the browser signs in) and an **API**
(the backend validates the token and exchanges it On-Behalf-Of the user). Skip this
whole step to run without auth (single shared `DefaultAzureCredential` identity).

### 3a. API app registration (the backend's audience)

1. **Entra ID → App registrations → New registration.** Name e.g. `foundry-assured-api`. Register.
2. **Expose an API → Add a scope.** Accept the default `api://<api-client-id>` Application ID URI. Scope name **`access_as_user`**, admins+users can consent.
3. **Certificates & secrets → New client secret.** Copy the **value** → this is `ENTRA_API_CLIENT_SECRET`.
4. **Manifest →** set `"requestedAccessTokenVersion": 2` (otherwise the backend rejects v1 tokens with "invalid claims").
5. **API permissions →** add the **delegated** permissions the OBO exchange needs, then **Grant admin consent**:
   - **Azure Machine Learning Services** (`user_impersonation`) — this is the app behind the `https://ai.azure.com` scope the Foundry client requests (it is *not* "Azure Cognitive Services").
   - **Azure Cognitive Search** (`user_impersonation`) — for `https://search.azure.com` (the knowledge base).
   > Find them by app id if the picker hides them: `az ad sp show --id 18a66f5f-dbdf-4c17-9dd7-1634712a9cbe` (AML) and `--id 880da380-985e-4c44-bf9a-...` (Search). They appear under *APIs my organization uses*.

### 3b. SPA app registration (the frontend)

1. **New registration.** Name e.g. `foundry-assured-spa`. Under *Redirect URI*, platform **Single-page application**, URI **`http://localhost:3000`** (add your deployed `WEB_URL` after Step 7).
2. **API permissions → Add → My APIs →** select the API app → delegated **`access_as_user`** → **Grant admin consent**.
3. If you sign in with a **personal/guest** account (live.com/gmail), the backend scheme sets `allow_guest_users=True` already; just make sure the account is a guest member of the tenant.

### 3c. Wire the ids into env

```bash
# apps/backend/.env
ENTRA_TENANT_ID=<tenant-id>
ENTRA_API_CLIENT_ID=<api-app-client-id>
ENTRA_API_CLIENT_SECRET=<the secret value from 3a.3>

# apps/frontend/.env.local   (cp .env.example .env.local first)
NEXT_PUBLIC_ENTRA_TENANT_ID=<tenant-id>
NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID=<spa-app-client-id>
NEXT_PUBLIC_ENTRA_API_CLIENT_ID=<api-app-client-id>
```

The frontend must run on **port 3000** (it must match the SPA redirect URI).

### 3d. App roles (RBAC) — required for HITL approval + the admin portal

Declare the four app roles on the **API** app and grant the app-only Microsoft Graph
permissions the in-portal user management needs:

```bash
ENTRA_API_CLIENT_ID=<api-app-client-id> ./scripts/setup-app-roles.sh
```

This is idempotent and:
- declares the four app roles — **Admin**, **Author**, **Approver**, **Reader**;
- grants the app-only Graph permissions (`User.ReadWrite.All`, `User.Invite.All`,
  `AppRoleAssignment.ReadWrite.All`, `Directory.Read.All`) and runs admin consent.

Then **assign yourself the Admin role**: **Entra → Enterprise applications → the API app →
Users and groups → Add user/group** → pick yourself → role **Admin**. The HITL approval
card requires **Approver** or **Admin**; the `/admin/users` portal requires **Admin**.

> Design & company-group→app-role mapping: [RBAC-AND-USER-MANAGEMENT-PLAN.md](./RBAC-AND-USER-MANAGEMENT-PLAN.md).

---

## Step 4 — Data-plane objects (KB + memory)

> **Fast path:** `./scripts/bootstrap.sh` runs the helpdesk ingest + memory (and fills
> `.env` from the azd outputs first). The manual commands:

```bash
cd apps/backend
uv run python -m cli.provision_memory      # create the Foundry memory store
```

These are **data-plane** (not Bicep), so you ingest each domain by hand. There are
**three domains, each with its own knowledge base + ingest** — deploy/ingest any subset
(at least one):

```bash
cd apps/backend

# Helpdesk KB — ~13 fake runbooks (a few minutes; the script polls until it settles)
uv run python -m app.knowledge.ingest

# Cockpit KB — point at a folder of Cockpit doc bundles
COCKPIT_DOCBUNDLES=/path/to/cockpit/docbundles \
  uv run python -m app.knowledge.ingest_cockpit

# Selfwiki KB — this repo's own deep-wiki (docs/wiki); reuses ingest_cockpit via ENV override
KB_KNOWLEDGE_SOURCE=selfwiki-docbundles-ks \
KB_DOMAIN_LABEL="o projeto foundry-assured" \
COCKPIT_STORAGE_CONTAINER=selfwiki-corpus \
COCKPIT_SEARCH_KNOWLEDGE_BASE=selfwiki-kb \
COCKPIT_SEARCH_INDEX=selfwiki-docbundles-ks-index \
COCKPIT_DOCBUNDLES=../../docs/wiki \
  uv run python -m app.knowledge.ingest_cockpit
```

Each ingest uploads its corpus → knowledge source → Foundry IQ knowledge base, stamps
the per-document access groups, and polls until the index settles.

### Generating the selfwiki corpus — two paths

The `docs/wiki` deep-wiki that the **selfwiki** ingest consumes is itself generated.
There are **two ways** to produce it:

1. **Foundry pipeline (`wiki_builder.py`)** — automated, runs in-cloud. From
   `apps/backend`: `uv run python -m app.knowledge.wiki_builder …`. Needs `azd up` done
   and the Foundry model (`gpt-5-mini`) deployed; it enforces the **build-fidelity gate**
   (rejects a low-fidelity bundle). This is the path that costs tokens.
2. **Microsoft Agent Skills** — no cloud, no cost. The skills under
   `apps/backend/app/knowledge/skills/{wiki-architect,wiki-page-writer}` are run by your
   IDE agent (**VS Code Copilot** or **Claude Code**): open the repo and ask it to
   *"create a wiki"* — the agent follows the skill instructions to write the bundle
   locally. (There is no `copilot plugin install` / slash command; it's the skills the
   IDE agent reads.)

Either path produces a doc bundle the selfwiki ingest above can index.

> **Citation style differs between the paths** (verified by actually running the Copilot CLI
> path on `infra/` — 100% of the source files it cited exist). The Foundry pipeline emits
> **repo-relative paths** (`infra/resources.bicep`); the Agent Skill resolves the git remote
> and emits **GitHub blob URLs** plus external/schema URLs and intra-wiki page links. The
> build-fidelity gate (`eval` / `wiki_builder._fidelity_report`) now **normalizes blob +
> external URLs**, so it scores the Foundry bundles cleanly (94–100%); but it still counts the
> skill's wiki-internal `.md` cross-links + prose, so it under-scores skill output. Validate a
> skill-generated bundle by **source-file existence** (do its cited files exist?), not the same
> gate threshold — the two are faithful, but not drop-in identical for the gate.

---

## Step 5 — Run locally

```bash
cd apps/backend  && uv run uvicorn app.main:app --port 8000 --reload
cd apps/frontend && npm install && npm run dev      # http://localhost:3000
```

Open <http://localhost:3000> — Overview, **/chat** (Live ⇄ Hosted toggle),
**/tickets**, **/evals**. Validate with `uv run python -m eval.run_eval`.

---

## Step 6 — Deploy the hosted agent (Foundry Agent Service)

```bash
azd env set AZURE_AI_PROJECT_ID "<project ARM id, ends in /projects/helpdesk-concierge>"
azd deploy helpdesk-concierge
azd ai agent show helpdesk-concierge        # status + endpoint + portal playground
azd ai agent invoke helpdesk-concierge "How do I roll back a bad deploy?"
```

**Post-deploy RBAC (required):** the platform creates a fresh managed identity for
the agent at deploy time, so it can't be pre-assigned in Bicep. Grant the agent's
*Instance Identity Principal ID* (from `azd ai agent show`):

```bash
AID=<instance-identity-principal-id>
ACC=<account ARM id .../accounts/aif-helpdesk-...>
SRCH=<search ARM id .../searchServices/srch-helpdesk-...>
az role assignment create --assignee-object-id $AID --assignee-principal-type ServicePrincipal \
  --role 53ca6127-db72-4b80-b1b0-d745d6d5456d --scope $ACC      # Azure AI User (call the model)
az role assignment create --assignee-object-id $AID --assignee-principal-type ServicePrincipal \
  --role 1407120a-92aa-4202-b7e9-c0e197c71c8f --scope $SRCH     # Search Index Data Reader (query the KB)
```

Without these the agent deploys but returns **403** at runtime.

---

## Step 7 — Publish backend + frontend (Azure Container Apps)

`NEXT_PUBLIC_*` are baked into the browser bundle at image build, so they must be
in the azd env before deploy. The helper script copies the values from your
`.env` files:

```bash
./scripts/set-deploy-env.sh            # sets NEXT_PUBLIC_* + ENTRA_* in the azd env from .env
azd up                                 # or: azd provision && azd deploy backend && azd deploy web
azd env get-values | grep WEB_URL      # then add  https://<web-fqdn>/  to the SPA redirect URIs (Step 3b)
```

Bicep wires the apps to each other by FQDN (no manual URL config) and grants the
shared identity ACR pull + Foundry/Search access. Images build remotely in ACR.

> **Cost:** the container apps are configured **`minReplicas: 0`** (scale-to-zero,
> idle = \$0) in `infra/containerapps.bicep`. They spin up on the first request and
> back down when idle. See [Cost & teardown](#cost--teardown) for the full picture.

---

## Step 8 (optional) — Safety & continuous-eval add-ons

```bash
cd apps/backend
uv run python -m eval.run_eval --safety                       # adversarial/jailbreak eval
uv run python -m cli.provision_guardrail --policy <rai-policy-arm-id>   # content-safety guardrail on the hosted agent
uv run python -m cli.provision_eval_rule --eval-id eval_xxx   # score the agent's live traces (eval_xxx from a --cloud run)
```

List the built-in RAI policies for `--policy`:
`az rest --method get --url "https://management.azure.com<account-arm-id>/raiPolicies?api-version=2024-10-01" --query "value[].name"`
(use the ARM id of `Microsoft.DefaultV2`).

---

## Agent evaluation (Foundry `ai-agent-evals` action)

The repo uses Microsoft's **official** [`microsoft/ai-agent-evals`](https://github.com/microsoft/ai-agent-evals)
GitHub Action to evaluate the **deployed hosted agent** (`helpdesk-concierge`) with
Foundry's hosted judges. Workflow: `.github/workflows/agent-evals.yml` (manual).

```bash
# absolute scores for the current agent (v3)
gh workflow run agent-evals.yml

# compare v3 against a baseline (v2) — confidence intervals + significance test
gh workflow run agent-evals.yml -f version=3 -f baseline=helpdesk-concierge:2
```

- **Dataset:** `apps/backend/eval/datasets/agent-evals.json` (generated from the golden
  set; `evaluators: groundedness, relevance, coherence, intent_resolution`).
- **Auth:** the same Azure OIDC + repo vars as the other cloud workflows.
- **Output:** scores land in the **Actions run summary**; with `baseline`, a side-by-side
  comparison with confidence intervals. *(Enable the repo Wiki for the full detailed view.)*
- **Advisory, not blocking** — see the workflow header for why (small golden set →
  hard-gate the deterministic ASSERTs in `ci.yml`, keep judge scores advisory until the
  set grows + judges are calibrated, then graduate to a baseline/CI gate).

## Cost & teardown

Pay-as-you-go, East US 2, USD. The numbers are order-of-magnitude — check the
[Azure pricing calculator](https://azure.microsoft.com/pricing/calculator/) for
your region/agreement. The table separates **fixed meters** (billed 24/7 whether
or not anyone uses the app) from **usage meters** (≈\$0 when idle).

| Resource | SKU | Cost | Kind |
| --- | --- | --- | --- |
| **Azure AI Search** | Basic | **~\$0.10/hr ≈ \$74/mo** | 🔴 fixed — runs 24/7, **the meter to watch** |
| Azure Container Registry | Basic | ~\$0.17/day ≈ **\$5/mo** | 🔴 fixed (already provisioned for the hosted agent) |
| Log Analytics | PerGB2018 | ~\$2.76/GB ingested · **\$0–3/mo** | 🟡 usage — demo telemetry is <1 GB/mo; 30-day retention free |
| Container Apps (backend + web) | Consumption, 0.5 vCPU / 1 GiB, **scale-to-zero** | **\$0 idle** · ~cents under demo load | 🟢 usage — within the monthly free grant (180k vCPU-s / 360k GiB-s / 2M req) |
| Hosted agent compute | — | **\$0 idle** | 🟢 deprovisions ~15 min after last call |
| Azure AI Foundry | Cognitive Services S0 | no fixed fee | 🟢 pay per token (below) |
| Model usage | `gpt-5-mini` GlobalStandard | ~\$0.25 / 1M input · ~\$2.00 / 1M output tok | 🟢 usage — a showcase is cents–few \$/mo |
| Embeddings | `text-embedding-3-*` | ~\$0.02 / 1M tok | 🟢 usage — negligible |
| Storage (blob corpus) | Standard_LRS | <\$1/mo | 🟢 usage |
| **Azure Files** (tickets) | 1 GiB share on the same account | ~\$0.06/mo + tiny txns → **cents** | 🟢 usage — persists `data/tickets.jsonl` across scale-to-zero |

**Bottom line:**
- **Marginal cost of the backend + web deploy** (Step 7): **~\$0–3/mo** — compute is scale-to-zero, the ACR already existed, so it's just a little Log Analytics ingestion.
- **Dominant cost overall: Azure AI Search ≈ \$74/mo if left on 24/7.** It has no scale-to-zero. If you're not actively using the showcase, **`azd down`** to stop that meter — it's ~95% of the bill.

```bash
azd ai agent delete helpdesk-concierge   # remove just the hosted agent
azd down --purge                         # delete the whole resource group (stops the AI Search meter)
```
