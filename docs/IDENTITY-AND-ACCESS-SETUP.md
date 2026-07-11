---
title: Identity & access setup — what's automated vs manual
description: The map of the Entra ID surface — what azd/Bicep creates, what you set up by hand (the app registrations), and why. Read this first when handing off the repo.
type: reference
audience: operator
status: stable
updated: 2026-06-29
---

# Identity & access setup — what's automated vs manual

The non-obvious thing when picking this repo up: **`azd up` does NOT create the Entra ID app
registrations.** It provisions the Azure resources and (optionally) the ACL *groups*, but the
**app registrations** (sign-in + OBO + CI) are a separate, mostly-manual step. This page is
the map so nobody has to rediscover it — the step-by-step lives in the linked docs; here is
*what creates what, and why.*

## The three layers

```mermaid
flowchart TB
  subgraph A["1 · Azure resources — AUTOMATED"]
    A1["azd up → infra/main.bicep + resources.bicep<br/>Foundry, AI Search, Storage, ACR,<br/>Container Apps, App Insights, role assignments"]
  end
  subgraph G["2 · Entra GROUPS — AUTOMATED (optional, Phase 4)"]
    G1["infra/entra/entra.bicep (Microsoft Graph Bicep extension)<br/>3 security groups for document-level ACL<br/>+ create-acl-identities.sh (test users/memberships)"]
  end
  subgraph R["3 · Entra APP REGISTRATIONS — MANUAL / scripted"]
    R1["scripts/setup-entra.sh → SPA app + API app (OBO)"]
    R2["CONTRIBUTING.md → CI app (GitHub OIDC + federated credentials)"]
  end
  A1 -->|"outputs feed env"| R1
  R1 -->|"client ids/secret as params"| A1
```

## What creates what

| Object | Created by | Automated? | Where |
| --- | --- | :---: | --- |
| Azure resources (Foundry, Search, Storage, Container Apps, …) + role assignments | `azd up` → `infra/main.bicep` | ✅ | [DEPLOYMENT.md Step 1](./DEPLOYMENT.md) |
| Entra **security groups** (public/internal/confidential) for the KB ACL | `infra/entra/entra.bicep` (MS Graph Bicep extension) | ✅ (separate, tenant-scoped deploy) | Phase 4 / [METHOD.md](./METHOD.md) |
| Demo **groups + test users** + memberships (ACL demo) | `infra/entra/create-acl-identities.sh` · `create-test-users.sh` | ✅ (script) | infra/entra/ |
| **API app registration** (backend audience, OBO) | `scripts/setup-entra.sh` *(or manual)* | ⚠️ semi | [DEPLOYMENT.md Step 3a](./DEPLOYMENT.md) |
| **SPA app registration** (frontend sign-in) | `scripts/setup-entra.sh` *(or manual)* | ⚠️ semi | [DEPLOYMENT.md Step 3b](./DEPLOYMENT.md) |
| **App roles** (Admin/Author/Approver/Reader) on the API app + app-only Graph permissions | `scripts/setup-app-roles.sh` | ⚠️ semi (you still assign yourself Admin in the portal) | [DEPLOYMENT.md Step 3d](./DEPLOYMENT.md) · [RBAC plan](./RBAC-AND-USER-MANAGEMENT-PLAN.md) |
| **CI app registration** (GitHub Actions OIDC + federated credentials) | manual `az ad app create` | ❌ | [CONTRIBUTING.md](../CONTRIBUTING.md) |
| Admin consent (Graph / Search `user_impersonation`) | manual (Entra admin) | ❌ | DEPLOYMENT Step 3 |

## The three app registrations

| App | What it's for | Produces (env / secret) |
| --- | --- | --- |
| **API** | the *audience* the backend validates; performs the **OBO** exchange (swaps the user's token for a Search token acting as them) | `ENTRA_API_CLIENT_ID`, `ENTRA_API_CLIENT_SECRET` |
| **SPA** | the frontend (MSAL) where the user **signs in** | `NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID` (+ `NEXT_PUBLIC_ENTRA_API_CLIENT_ID`, `_TENANT_ID`) |
| **CI** | lets **GitHub Actions** sign in to Azure with no secret, via **OIDC + federated credentials** | repo vars `AZURE_CLIENT_ID` / `_TENANT_ID` / `_SUBSCRIPTION_ID` |

> The CI app's **federated credential** references the **repo name** in its subject
> (`repo:<owner>/<repo>:ref:refs/heads/main` and `…:environment:production`). **If the repo is
> renamed, update the subject** (`az ad app federated-credential update`), or the jobs that
> sign in to Azure (deploy, security-gates, eval-cloud) stop authenticating. The basic CI
> (lint/build/typecheck) doesn't use OIDC and keeps working.
> *(Already done for this repo: the subjects were updated to `repo:ruinosus/foundry-assured`
> after the rename.)*

## The On-Behalf-Of chain (grounded answers as the user)

The grounded domains (Cockpit, Selfwiki) answer **as the signed-in user** via On-Behalf-Of (OBO), so
inference is attributable and per-user document ACL works. That's a **three-tier OBO chain** —
`SPA → API app → downstream` — and it has three requirements, all set by `scripts/setup-entra.sh`:

```mermaid
flowchart LR
  U[User signs in] -->|MSAL| SPA
  SPA -->|"token (aud = API app)"| API[API app]
  API -->|"OBO exchange"| AI["ai.azure.com<br/>(Foundry inference)"]
  API -->|"OBO exchange"| S["search.azure.com<br/>(KB retrieval)"]
```

| # | Requirement | Where | Symptom if missing |
| --- | --- | --- | --- |
| 1 | API app holds the **delegated** `user_impersonation` on **ai.azure.com** (`18a66f5f-…`) + **search.azure.com** | `setup-entra.sh` (`az ad app permission add`) | OBO can't get a downstream token |
| 2 | **Admin consent** on the API app for those delegated permissions | `setup-entra.sh` (`admin-consent`) | OBO returns `interaction_required` / consent error |
| 3 | **SPA registered as a `knownClientApplications` of the API app** | `setup-entra.sh` (`az rest PATCH … knownClientApplications`) | **The browser 403s on inference** — the OBO of a *SPA-issued* token to the downstream returns a token that isn't authorized, even though (1)+(2) are in place. A *direct* API-app token OBO's fine, which is why it's easy to miss. |

Requirement **(3)** is the non-obvious one: consent to the SPA must **cascade** to the API's downstream
permissions (combined consent), which only happens when the SPA is a known client of the API. Verified
in-session: with (3) missing the deployed `/cockpit` streamed `RUN_ERROR: 403` for signed-in users
even though a direct API-app→OBO→Responses call returned 200.

Beyond the app registrations, each **app user needs `Foundry User`** on the Foundry account (they run
inference as themselves) — granted to a group via `infra/resources.bicep` (`appUsersGroupId` →
`APP_USERS_GROUP_ID`). And the backend/deploying identities need the Search roles in that same Bicep.

## Why the app registrations aren't in Bicep

1. **Secret**: the OBO app needs a client secret — you don't want Bicep generating/exposing a secret in a plaintext output.
2. **Admin consent**: the delegated permissions require admin consent — an interactive, non-declarative step.
3. **Separation**: identity (apps) is usually a different process/team than infra.
4. The Graph Bicep extension *could* create `Microsoft.Graph/applications`, but for reasons (1)–(3) we use a script + parameters instead. (The **groups**, which don't have those problems, *are* in Bicep.)

## Gotcha: what survives `azd down`

`azd down` deletes **only the resource group** (the Azure resources). **The Entra objects
persist**: app registrations, groups, and users **remain** in the tenant. So:

- Re-running `azd up` does **not** recreate the app regs — reuse the existing ones (the `ENTRA_*` values stay valid).
- Client secrets **expire** (rotate when they do).
- To truly reset identity, delete the app regs/groups by hand (`az ad app delete`, `az ad group delete`).

## Handoff — from zero to running

1. **Infra:** `azd up` → [DEPLOYMENT.md Step 1](./DEPLOYMENT.md).
2. **App regs (sign-in + OBO):** `scripts/setup-entra.sh` (idempotent) → [Step 3](./DEPLOYMENT.md). Skip if you'll run **without sign-in** (single `DefaultAzureCredential`).
3. **App roles (RBAC):** `ENTRA_API_CLIENT_ID=<api> scripts/setup-app-roles.sh`, then assign yourself **Admin** in the portal → [Step 3d](./DEPLOYMENT.md). Needed for HITL approval (Approver/Admin) + the `/admin/users` portal (Admin).
4. **CI (OIDC):** create the CI app + federated credentials → [CONTRIBUTING.md](../CONTRIBUTING.md); set the repo vars/secrets.
5. **ACL (optional, Phase 4):** deploy `infra/entra/entra.bicep` + `create-acl-identities.sh` → [METHOD.md](./METHOD.md).
6. **Data:** ingest the KBs → [DEPLOYMENT.md Step 4](./DEPLOYMENT.md).

If you're **only running/demoing** without multi-user, steps 2–5 are optional: the app falls
back to `DefaultAzureCredential` and auth is simply off.
