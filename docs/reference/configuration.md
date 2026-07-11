---
title: Configuration
description: The environment variables that drive the backend and frontend, grouped by concern.
type: reference
audience: operator
status: stable
updated: 2026-07-11
---

# Configuration

Both apps are configured by environment. The canonical, always-current lists are the
`.env.example` files (`apps/backend/.env.example`, `apps/frontend/.env.example`); this page groups
the load-bearing knobs by concern. Fill the backend `.env` from `azd env get-values` after
`azd up`. Auth is always `DefaultAzureCredential` — **no keys in config**.

## Backend — Foundry & Azure

| Variable | Purpose |
|---|---|
| `FOUNDRY_PROJECT_ENDPOINT` | the Foundry project the backend calls |
| `FOUNDRY_MODEL` | chat model deployment (safe default: `gpt-5-mini`) |
| `FOUNDRY_EMBEDDING_MODEL` | embedding deployment (`text-embedding-3-small`) |
| `AZURE_AI_OPENAI_ENDPOINT` | Azure OpenAI endpoint |
| `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KNOWLEDGE_BASE` | Azure AI Search + the Foundry IQ KB |
| `AZURE_STORAGE_ACCOUNT`, `AZURE_STORAGE_RESOURCE_ID`, `AZURE_STORAGE_CONTAINER` | the corpus blob store |
| `FOUNDRY_MEMORY_STORE` | the per-user memory store |

## Backend — identity & tenancy

| Variable | Purpose |
|---|---|
| `ENTRA_TENANT_ID`, `ENTRA_API_CLIENT_ID`, `ENTRA_API_CLIENT_SECRET` | the API app registration (OBO exchange) |
| `ENTRA_SPA_CLIENT_ID` | the SPA app registration |
| `DEPLOYMENT_MODE` | `self_hosted` (default) · `dedicated` · `shared` — the deployment-mode seam ([ADR-007](../adr/ADR-007-coexistence-deployment-mode.md)) |
| `ONBOARDING_ALLOWED_TIDS` | the Entra `tid`s allowed in shared mode |
| `APP_USERS_GROUP_ID` | the app-users group (Graph) |
| `FRONTEND_ORIGIN` | CORS allow-list for the frontend |

## Backend — access control (data, not code)

Access **follows the source**; there is no classification logic in code. See
[the assurance mechanism](../METHOD.md) and [RBAC plan](../RBAC-AND-USER-MANAGEMENT-PLAN.md).

| Variable | Purpose |
|---|---|
| `ACL_CLASSIFICATION` | classification → source mapping |
| `ACL_GROUP_MAP` | group name → Entra object-ID resolution |
| `ACL_PUBLIC_GROUP`, `ACL_INTERNAL_GROUP`, `ACL_CONFIDENTIAL_GROUP` | the classification groups |
| `ACL_DEFAULT_GROUPS` | fail-closed default when a doc declares no access |

## Backend — domains & prompts

Each grounded domain has its own KB/index/container/hosted-agent knobs
(`COCKPIT_*`, `SELFWIKI_*`), plus the hosted-agent names (`HOSTED_AGENT_NAME`,
`PLATFORM_HOSTED_AGENT_NAME`) and `MCP_ENABLED` for the platform domain.

| Variable | Purpose |
|---|---|
| `DNA_BASE_DIR` | where the runtime prompt scope is read from — local disk, or the Azure Files mount `/mnt/dna` in prod ([ADR-014](../adr/ADR-014-runtime-prompt-scope-no-rebuild.md)) |
| `COCKPIT_*`, `SELFWIKI_*` | per-domain KB / index / storage / hosted-agent settings |
| `HOSTED_AGENT_NAME`, `PLATFORM_HOSTED_AGENT_NAME` | the deployed hosted agents |
| `MCP_ENABLED` | enable the platform domain's MCP tool servers |

## Frontend

| Variable | Purpose |
|---|---|
| `BACKEND_URL` | the backend the CopilotKit runtime proxies to |
| `NEXT_PUBLIC_ENTRA_TENANT_ID`, `NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID`, `NEXT_PUBLIC_ENTRA_API_CLIENT_ID` | browser-baked sign-in config (compiled into the bundle at build) |
| `NEXT_PUBLIC_DEMO_MODE` | replay recorded AG-UI fixtures — no Azure, no backend |

> [!NOTE]
> `NEXT_PUBLIC_*` values are **compiled into the frontend bundle at image build**, so set them in
> the azd env *before* building the container image (see [Deploy from zero](../DEPLOYMENT.md)).
