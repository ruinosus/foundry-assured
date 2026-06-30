# D-packaging runbook — marketplace publish, Lighthouse delegation, hosted deploy

> **Infra-gated.** Every step below requires an external account or a live Azure
> subscription/tenant (Partner Center, the customer's subscription, a deployed
> Foundry project). **None of it runs in CI** and nothing here has been executed —
> this runbook is the *vehicle* for the infra-gated parts of sub-project
> D-packaging. The Bicep/ARM artifacts it references are authored and compiled
> offline (`az bicep build`); the publish, the cross-tenant delegation, and the
> live tool resolution are exercised by a human operator against real tenants.
>
> See: [ADR-001](./adr/ADR-001-tenancy-deployment-stamps.md) ·
> [ADR-002](./adr/ADR-002-dedicated-stamp-managed-app-lighthouse.md) ·
> [ADR-011](./adr/ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md) ·
> [D-packaging verifications](./superpowers/notes/d-packaging-verifications.md)

## What this delivers

The two delivery vehicles from ADR-001/ADR-002:

| Vehicle | Model | Artifact | Who deploys |
|---|---|---|---|
| **Managed Application** | Dedicated stamp (enterprise) | `infra/managed-app/managed-app.zip` (`mainTemplate.json` + `createUiDefinition.json`) | Customer, from the marketplace, into their subscription |
| **Azure Lighthouse** | Shared-model data-plane management | `infra/lighthouse/lighthouse.bicep` + `parameters.json` | Customer, into their subscription, delegating scopes to our tenant |

After either lands, the publisher completes the runtime: deploy the
`platform-concierge` hosted agent and provision the per-tenant Foundry Toolbox
(ADR-011).

---

## Step A — Publish the Managed Application to Partner Center

**Prerequisite:** a **Partner Center** account enrolled in the *Commercial
Marketplace* program (publisher management). Not available in CI.

1. **Build the package** (local, no external account needed):
   ```bash
   cd infra/managed-app
   ./build.sh
   # -> mainTemplate.json (compiled from managedApp.bicep) + managed-app.zip
   ```
   `mainTemplate.json` is committed; `managed-app.zip` is a build output
   (gitignored). The zip is `mainTemplate.json` + `createUiDefinition.json`
   zipped flat (Partner Center requires both at the archive root).

2. **Create the offer.** In Partner Center → *Marketplace offers* → **Azure
   Application** → new offer. Add a **plan** of type **Managed application**.

3. **Upload the package.** On the plan's *Technical configuration*, upload
   `managed-app.zip`.

4. **Plan settings (publisher management).**
   - **Deployment mode:** choose **Incremental** unless you specifically want the
     managed RG reset on each update. *Complete* mode deletes resources in the
     managed RG that are absent from the template on redeploy — only use it if
     you accept that destructive reconciliation. Default to **Incremental** for a
     stamp that accrues runtime state (tickets file share, Foundry connections).
   - **Authorizations / publisher access:** grant the publisher's managing
     identity (the same principal used for Lighthouse, Step C) the operator role
     on the managed RG, so we can operate the stamp the customer cannot directly
     modify (ADR-002).
   - **Notification endpoint:** set the webhook for create/update/delete events.

5. **Review + publish.** Submit for certification. **This is the infra-gated
   action — it requires the live Partner Center account and has not been done
   here.**

> **Validation that *is* runnable offline** (already covered by Task 4):
> `az bicep build` compiles `managedApp.bicep` → `mainTemplate.json` clean. For a
> deeper structural pass, run **ARM-TTK** against the package and test
> `createUiDefinition.json` in the **CreateUiDefinition sandbox**
> (`https://portal.azure.com/#blade/Microsoft_Azure_CreateUIDef/SandboxBlade`).

---

## Step B — Customer deploys the Managed Application

**Prerequisite:** the **customer's** Azure subscription + a user with rights to
create a Managed Application there. (Publisher cannot do this on the customer's
behalf — that's the point of the model.)

1. Customer opens the offer in the marketplace → **Create**.
2. The portal renders `createUiDefinition.json`: the customer sets
   **modelDeploymentName** (defaults to the secure `gpt-5-mini`) and, optionally,
   the **Entra OBO** fields (tenant + backend API client id/secret). Blank OBO
   fields deploy the stamp without On-Behalf-Of.
3. The platform creates a **managed resource group** in the customer's
   subscription and deploys `mainTemplate.json` into it: Foundry account +
   project + model, Azure AI Search KB, storage, ACR, the shared app identity,
   and the backend + web Container Apps.
   - `principalId` is **empty** in the managed-app path: no deploying-user
     data-plane grant is created (the publisher operates the stamp; the
     conditional caller role assignments in `resources.bicep` are skipped —
     fail-closed by default).
4. Outputs `BACKEND_URL` / `WEB_URL` are surfaced on the managed-app resource.

---

## Step C — Customer delegates scopes via Azure Lighthouse (shared model)

**Prerequisite:** the **customer's** subscription (a user who can create a
`Microsoft.ManagedServices` registration there) **and** our **managing tenant ID**
+ the **operator principal object ID** in our tenant.

This is the *shared-model* path (not the dedicated stamp): instead of operating a
managed app, the customer **delegates specific scopes** to our tenant so we manage
their data-plane cross-tenant. Revocable and auditable (ADR-002).

1. Fill `infra/lighthouse/parameters.json`:
   - `managedByTenantId` — **our** managing tenant ID.
   - `principalId` — object ID (in our tenant) of the operator user/group/SP.
   - `principalIdDisplayName` — friendly name shown in the customer's activity log.
2. Customer deploys at **subscription scope** (from their subscription):
   ```bash
   az deployment sub create \
     --name foundry-helpdesk-lighthouse \
     --location <region> \
     --template-file infra/lighthouse/lighthouse.bicep \
     --parameters @infra/lighthouse/parameters.json
   ```
3. This registers our tenant as a managed-service provider and assigns a
   **least-privilege** role set at the delegated scope: **Reader** +
   **Monitoring Contributor** + **Log Analytics Reader** (no Owner, no
   Contributor — we operate and observe, we don't own).
4. **Revocation:** the customer can remove the **registration assignment**
   (`Microsoft.ManagedServices/registrationAssignments`) at any time; the
   delegation disappears and every prior action stays attributed in their
   activity log.

> **Validation offline:** `az bicep build --file infra/lighthouse/lighthouse.bicep`
> compiles clean. The built-in role GUIDs are real (cross-checked with
> `az role definition list`). The actual cross-tenant delegation is infra-gated.

---

## Step D — Deploy the platform hosted agent + provision the Foundry Toolbox

**Prerequisite:** a **deployed Foundry project** (from Step B's managed app, or an
azd-provisioned project) and `azd` authenticated against it.

The `platform-concierge` hosted agent carries **write-approval HITL**, so it uses
the **Invocations** protocol (not Responses) — see ADR-011. Its tools resolve
through a **Foundry Toolbox** with **OAuth identity passthrough** (per-tenant, OBO),
so the container never handles credentials.

1. **Deploy the hosted agent** (azd service `platform-concierge` →
   `apps/hosted-platform`, `host: azure.ai.agent`):
   ```bash
   azd deploy platform-concierge
   ```
   The container serves the same AG-UI agent we run at `/platform` via
   `InvocationsHostServer` (so the write-approval interrupt survives end-to-end).

2. **Provision the Foundry Toolbox** (ADR-011) in the project. The Toolbox is the
   central tool-auth broker; the hosted agent references it by name. The Toolbox
   CRUD API (`project.beta.toolboxes.*`) is verified in `azure-ai-projects` 2.2.0
   (see [verifications](./superpowers/notes/d-packaging-verifications.md)), but
   the **Toolbox↔hosted-agent binding** is a deploy-time fact (infra-gated).

3. **Wire `FOUNDRY_TOOLBOX_NAME`.** Set the env var on the hosted agent to the
   Toolbox name; `apps/hosted-platform/main.py` reads it to resolve its MCP tools
   at runtime. (That file fences the binding with `TODO(infra-gated)` — the
   binding is configured here at deploy, not in container code.)

4. **Map per-connection tools (DATA, not code).** For each platform MCP server,
   set its `project_connection_id` (a named Foundry connection) on the Toolbox —
   and where applicable `connector_id` / `authorization`. **OAuth identity
   passthrough is DATA on the connection** (rule #6 / ADR-011): the tool runs as
   the signed-in user via OBO; no header provider, no hand-rolled credentials.
   First-use consent is gathered per user (preview — exercise with a real user).

> **Infra-gated literals** (per rule #1, not fabricated): the Invocations auth
> scope and the AG-UI request envelope/SSE framing are confirmed live against the
> deployed agent; the Toolbox binding + per-connection mapping are deploy-time. All
> are tracked as `TODO(infra-gated)` in the relevant backend/container code and
> resolved here, against real infra.

---

## Quick reference — where each artifact lives

| Artifact | Path | Built/validated by |
|---|---|---|
| Managed App root template (Bicep) | `infra/managed-app/managedApp.bicep` | `az bicep build` (compiles clean) |
| Managed App root template (ARM) | `infra/managed-app/mainTemplate.json` | generated by `build.sh` |
| Create UI definition | `infra/managed-app/createUiDefinition.json` | CreateUiDefinition sandbox |
| Marketplace package | `infra/managed-app/managed-app.zip` | `build.sh` (gitignored output) |
| Lighthouse delegation | `infra/lighthouse/lighthouse.bicep` + `parameters.json` | `az bicep build` (compiles clean) |
| Platform hosted agent | `apps/hosted-platform/` (azd `platform-concierge`) | `azd deploy` (infra-gated) |
