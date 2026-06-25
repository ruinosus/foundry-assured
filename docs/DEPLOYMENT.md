# Deployment & provisioning guide

End-to-end: from a fresh `git clone` to a fully provisioned, optionally
cloud-published Foundry Helpdesk. Read top to bottom the first time.

> Architecture & repo layout: [`../README.md`](../README.md). This doc is the
> operational runbook.

## What gets provisioned

| Layer | How | Where |
| --- | --- | --- |
| Foundry account + project + models, Azure AI Search, Storage, ACR, Container Apps env, RBAC | **Bicep** via `azd up` (control plane) | `infra/` |
| Knowledge base + memory store | **Python scripts** (data plane) | `apps/backend/{app/knowledge/ingest.py, cli/}` |
| Entra app registrations (SPA + API) for sign-in + OBO | **manual** (portal) — see Step 3 | — |
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
`gpt-4.1-mini` + `text-embedding-3-small` deployments, **Azure AI Search (Basic)**,
a Storage account, an **ACR**, a **Container Apps environment**, a shared managed
identity, and all keyless role assignments.

Region tips: pick where `gpt-4.1-mini` GlobalStandard has quota (e.g. `eastus2`);
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

This is the only **manual** part, and the easiest to get wrong. You create **two**
app registrations: a **SPA** (the browser signs in) and an **API** (the backend
validates the token and exchanges it On-Behalf-Of the user). Skip this whole step
to run without auth (single shared `DefaultAzureCredential` identity).

### 3a. API app registration (the backend's audience)

1. **Entra ID → App registrations → New registration.** Name e.g. `foundry-helpdesk-api`. Register.
2. **Expose an API → Add a scope.** Accept the default `api://<api-client-id>` Application ID URI. Scope name **`access_as_user`**, admins+users can consent.
3. **Certificates & secrets → New client secret.** Copy the **value** → this is `ENTRA_API_CLIENT_SECRET`.
4. **Manifest →** set `"requestedAccessTokenVersion": 2` (otherwise the backend rejects v1 tokens with "invalid claims").
5. **API permissions →** add the **delegated** permissions the OBO exchange needs, then **Grant admin consent**:
   - **Azure Machine Learning Services** (`user_impersonation`) — this is the app behind the `https://ai.azure.com` scope the Foundry client requests (it is *not* "Azure Cognitive Services").
   - **Azure Cognitive Search** (`user_impersonation`) — for `https://search.azure.com` (the knowledge base).
   > Find them by app id if the picker hides them: `az ad sp show --id 18a66f5f-dbdf-4c17-9dd7-1634712a9cbe` (AML) and `--id 880da380-985e-4c44-bf9a-...` (Search). They appear under *APIs my organization uses*.

### 3b. SPA app registration (the frontend)

1. **New registration.** Name e.g. `foundry-helpdesk-spa`. Under *Redirect URI*, platform **Single-page application**, URI **`http://localhost:3000`** (add your deployed `WEB_URL` after Step 7).
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

---

## Step 4 — Data-plane objects (KB + memory)

```bash
cd apps/backend
uv run python -m app.knowledge.ingest      # upload corpus → knowledge source → Foundry IQ knowledge base
uv run python -m cli.provision_memory      # create the Foundry memory store
```

These are **data-plane** (not Bicep). Ingestion indexes ~13 runbooks (a few
minutes; the script polls until it settles).

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

> **Cost:** the container apps default to `minReplicas: 1` (always-on). For
> scale-to-zero (idle = \$0), set `minReplicas: 0` in `infra/containerapps.bicep`.

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

## Cost & teardown

| Resource | Cost | Note |
| --- | --- | --- |
| Azure AI Search (Basic) | ~\$0.10/hr | the meter that runs 24/7 |
| ACR (Basic) | ~\$5/mo | |
| Container Apps (min 1 replica) | a few \$/mo each | set `minReplicas: 0` for scale-to-zero |
| Hosted agent compute | **\$0 idle** | deprovisions after 15 min |
| Models | per token | |

```bash
azd ai agent delete helpdesk-concierge   # remove just the hosted agent
azd down --purge                         # delete the whole resource group (stops the AI Search meter)
```
