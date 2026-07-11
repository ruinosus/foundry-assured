---
title: 'Design: Sub-project D-packaging — hosted agent + dedicated stamp + leftovers'
description: Complete D — deploy the platform hosted agent for real (Invocations + Foundry Toolbox per-tenant + write-approval HITL), author the dedicated-stamp marketplace artifacts (Managed Application + Lighthouse) as structurally-validated IaC, and finish the small deferred code (tier→domains, PerRequest cleanup, #3199 live verify).
type: design
audience: contributor
status: draft
updated: 2026-06-29
---

# Sub-project D-packaging — hosted agent + dedicated stamp + leftovers

> Second and final slice of D (after **D-runtime**, merged via PR #80 into `develop`). One spec, three
> internally-bounded **phases**, each with an infra-free deliverable (authored + structurally validated
> now) and an infra-gated validation (deployed Foundry / Partner Center / customer tenants). Builds on
> **A–D-runtime** and the MCP integration. Decisions:
> [ADR-001](../../adr/ADR-001-tenancy-deployment-stamps.md) (stamps),
> [ADR-002](../../adr/ADR-002-dedicated-stamp-managed-app-lighthouse.md) (Managed App + Lighthouse),
> [ADR-009](../../adr/ADR-009-native-tool-approval-foundry-connection-resolution.md),
> [ADR-010](../../adr/ADR-010-per-tenant-domain-entitlement.md), and the new
> **[ADR-011](../../adr/ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md)** (hosted Toolbox passthrough).

## Goal

Finish D: (1) **deploy the platform hosted agent for real** over the **Invocations** protocol, with
per-tenant tools via the **Foundry Toolbox + OAuth identity passthrough** and write-approval HITL
preserved, and make `stream_platform_agui` stream it (replacing D-runtime's skeleton); (2) **author the
dedicated-stamp artifacts** — an Azure **Managed Application** package (`mainTemplate.json` +
`createUiDefinition.json`) + an Azure **Lighthouse** delegation template — as structurally-validated IaC,
with real publish/delegation infra-gated; (3) **finish the small deferred code**: the tier→domains
entitlement map, collapsing the `PerRequest*` proxies, and the #3199 write-approval-over-AG-UI live
verification.

## Scope boundary

- **D-packaging owns:** the deployed hosted platform agent + the real Invocations streaming; the Managed
  App + Lighthouse IaC + publish runbook; tier→domains; the `PerRequest*` cleanup; the #3199 live verify.
- **Already done** (A–D-runtime, MCP): the deployment-mode seam, the tenant store/connections, the
  credential brokering + RBAC + native tool-approval, shared-mode enablement + DomainAssignment, the
  `/platform-hosted` route + skeleton + frontend toggle.
- **Out of scope:** any new product domain; pricing-tier definitions beyond the `TIER_DOMAINS` hook.

## Non-goals

- Marketplace *publish* and real-tenant Lighthouse delegation (infra-gated runbooks — need a Partner
  Center account + a customer subscription; we never fabricate a "published" claim).
- Re-implementing AG-UI for the hosted path — Invocations passes the AG-UI stream **untouched**, so the
  deployed agent reuses the existing AG-UI platform agent.
- Storing/reading any secret on the hosted path — the Foundry Toolbox brokers tool auth (ADR-011).

## Phase 1 — Hosted platform agent (full parity)

The deployed agent serves the **same** AG-UI platform agent with the **same governance as live `/platform`**
(per-tenant tools + write-approval HITL), and `stream_platform_agui` streams it for real.

**Web-verified design refinement (resolves D-runtime Task 0's open caveat):** the Invocations SSE
"envelope" is **AG-UI itself** — Microsoft: *"AG-UI is itself an SSE event stream… Invocations lets the
AG-UI bytes flow through Foundry untouched."* So there is no separate envelope to reverse-engineer (Task 0
worried there was). Two consequences: the container reuses the existing AG-UI agent, and the bridge is an
AG-UI passthrough proxy.

```mermaid
flowchart LR
    UI["browser (CopilotKit, AG-UI)"] -->|toggle: hosted| BR["stream_platform_agui (AG-UI passthrough proxy)"]
    BR -->|POST /protocols/invocations| HA["deployed agent: InvocationsHostServer<br/>(serves the SAME AG-UI platform agent)"]
    HA -->|tools| TB["Foundry Toolbox MCP endpoint<br/>OAuth identity passthrough (per-user/tenant)"]
    HA -->|AG-UI SSE (incl. write-approval interrupt) untouched| BR --> UI
```

**Components:**
1. **`apps/hosted-platform/`** (new; mirrors the `apps/hosted-agent/` **file layout only**, NOT its
   content) — `main.py` wraps the platform agent in **`InvocationsHostServer`**
   (`agent_framework_foundry_hosting`; the Invocations analog of the `ResponsesHostServer` the existing
   agents use; serves `POST /invocations` on port 8088). **Critical inversion:** the existing
   `hosted-agent`/`hosted-cockpit` are *deliberately stripped, single-identity Responses* variants
   (no OBO/HITL); `hosted-platform` does the **opposite** — it serves the **same AG-UI agent** we run at
   `/platform`, keeping per-tenant + write-approval HITL. So do NOT copy hosted-agent's workflow-rebuild /
   single-identity stripping — only the file scaffold. **Which agent object the host server wraps (load-bearing,
   step-0):** `build_platform_agent()` with its MCP tools resolved through the **Foundry Toolbox** (OAuth
   passthrough supplies per-user identity) rather than the live path's `build_mcp_tools()` — there is no
   per-request HTTP auth context in the container; identity arrives via the Toolbox. `agent.yaml` declares the
   Invocations protocol; `Dockerfile` + `requirements.txt` mirror the existing hosted agents.
2. **`azure.yaml`** — a 3rd `host: azure.ai.agent` service `platform-concierge` → `apps/hosted-platform`
   (matches `platform_hosted_agent_name`).
3. **Per-tenant tools via Foundry Toolbox + OAuth passthrough** ([ADR-011](../../adr/ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md)) — the deployed agent
   resolves MCP tools through the Toolbox MCP endpoint, which brokers auth (OAuth identity passthrough for
   per-user/tenant). C's `build_hosted_from_connections` lands as **Toolbox configuration**, not in-container
   credential code.
4. **Real `stream_platform_agui`** (`app/services/hosted.py`) — replace the `NotImplementedError` with an
   **AG-UI passthrough**: POST the run to `{foundry_project_endpoint}/agents/{platform_hosted_agent_name}/endpoint/protocols/invocations`
   (auth via the request's credential), stream the raw SSE back to the browser — the bytes are already AG-UI
   (incl. the `request_info` write-approval interrupt the `TicketApproval.tsx` tap consumes; the resume
   round-trips back over Invocations). The clean-error path stays for the no-endpoint case.

**Infra-free now:** the container imports + `agent.yaml` well-formed (`hosted_platform_smoke_test`); the
bridge keeps the clean envelope/error on no-endpoint (`platform_hosted_bridge_test` stays green).
**Infra-gated (azd up + deployed agent + Toolbox):** the real Invocations streaming, the per-tenant Toolbox
resolution (incl. the consent-link first-use flow — preview rough edge per ADR-011), and the write-approval
round-trip (`platform_hosted_e2e` gets a real body).

**Plan step-0 verification (rule #1):** confirm the exact `InvocationsHostServer` import/signature in the
installed `agent_framework_foundry_hosting`, and the Toolbox config surface, before the container/bridge
rely on them. (The AG-UI-untouched property removes the envelope unknown; the host-server class + Toolbox
config remain to verify.)

## Phase 2 — Dedicated stamp (Managed App + Lighthouse IaC)

Author the marketplace artifacts now (structurally validated offline); real publish/delegation infra-gated.

**Components:**
1. **`infra/managed-app/`** — the Managed Application package. A marketplace Managed App is a root
   `mainTemplate.json` (ARM, the control-plane resources deployed into the *customer's* managed resource
   group) + `createUiDefinition.json` (deploy-time parameter UI). **DRY path:** author the managed-app
   deployment in **Bicep that composes the existing `infra/` modules** (`resources.bicep`,
   `containerapps.bicep`), then `bicep build` → `mainTemplate.json` (extends
   [ADR-002](../../adr/ADR-002-dedicated-stamp-managed-app-lighthouse.md)) — so resource definitions aren't
   duplicated; the managed-app template is a customer-subscription re-parameterization of the same modules.
2. **`createUiDefinition.json`** — region, Entra app-registration ids, Foundry project pointers, sizing.
   Validated with the createUiDefinition sandbox + ARM-TTK.
3. **`infra/lighthouse/`** — a `Microsoft.ManagedServices` registration (definition + assignment) the
   customer deploys to delegate specific subscriptions/RGs to our managing tenant — **least-privilege,
   revocable, auditable** (ADR-002); the shared-model data-plane management vehicle.
4. **Package/build step** — a script (`infra/managed-app/build.sh`) that `bicep build`s and zips
   `mainTemplate.json` + `createUiDefinition.json` (+ optional `viewDefinition.json`) at the package root.

**Validation — infra-free now:** `bicep build` compiles `mainTemplate.json`; **ARM-TTK (`Test-AzTemplate`)**
lints `mainTemplate.json` + `createUiDefinition.json` (or, if the toolchain isn't present locally, the lint
is the documented offline gate); the package zip assembles with the required root layout. **Infra-gated
(runbook, not fabricated passes):** Partner Center publish, customer-subscription deploy, Lighthouse
delegation against a real tenant.

## Phase 3 — Leftovers

1. **tier→domains entitlement map** (closes [ADR-010](../../adr/ADR-010-per-tenant-domain-entitlement.md)
   Open Q#3). A data-driven `TIER_DOMAINS: dict[str, tuple[str, ...]]` in `app/core/tenant.py` (`"shared" →
   DOMAIN_IDS`, room for a smaller `"starter"` set). `POST /tenant/onboard` accepts an optional `tier`
   (Admin-gated via the existing `onboarding_guard`) and seeds `enabled_domains = TIER_DOMAINS.get(rec.tier,
   DOMAIN_IDS)`. Unknown/unset tier → `DOMAIN_IDS` (preserves today's "all by default", non-breaking).
   **Note:** `onboard()` today has **no request body** (it takes only `user: User = Depends(onboarding_guard)`),
   so this introduces a small `OnboardBody(BaseModel)` with an optional `tier: str | None` (the plan names it). The
   request-time `require_domain` gate stays fail-closed regardless. Infra-free unit-tested.
2. **Collapse `PerRequestPlatformAgent` into `PerRequestAgent`** (the Task-4 reviewer's flagged debt). Add
   optional `name`/`description` overrides to `PerRequestAgent`; express the platform proxy as
   `PerRequestAgent("platform", build_platform_agent, name="PlatformConcierge", description=…)`; delete the
   duplicate class. Pure refactor — `isinstance(…, SupportsAgentRun)` holds, per-request build unchanged,
   **self-hosted byte-identical**. Infra-free unit-tested.
3. **#3199 / write-approval-over-AG-UI live verification.** Now that the platform agent (live *and* hosted)
   carries write tools with per-tool `approval_mode`, run the **live** check: running stack + a write tool →
   confirm `always_require_approval` fires over AG-UI and the `TicketApproval.tsx` tap consumes + resumes.
   **Conditional deliverable:** if unfixed in the installed `agent-framework`, implement the framework
   `RequestInfoEvent`-emitting **middleware fallback** (ADR-009's stated fallback). Infra-gated (running
   stack); procedure + conditional middleware authored.

## Error handling, testing, infra-gating

**Error handling:** the bridge surfaces a clean AG-UI `RunErrorEvent` when the agent is unreachable/undeployed
(unchanged from the skeleton); Toolbox auth failures (incl. the preview passthrough rough edge) surface as a
tool error, never a hang; a write on an unverified hosted path is gated by the same approval as live (no
silent un-approved write); the stamp build fails loudly on a malformed template (ARM-TTK).

**Testing (repo convention: runnable `def main()->int` in `apps/backend/eval/`, NO pytest; frontend: `tsc`):**
- *Infra-free:* `tier_domains_test`; `per_request_override_test`; `hosted_platform_smoke_test` (container
  imports + `agent.yaml` well-formed); `platform_hosted_bridge_test` stays green; Managed App `bicep build`
  compiles + ARM-TTK lint (where the toolchain is present, else documented).
- *Infra-gated (skip clean / runbook):* the expanded `platform_hosted_e2e` (real Invocations streaming +
  Toolbox per-tenant + write-approval round-trip); shared multi-tenant flow; #3199 live; Managed App publish
  + customer-sub deploy; Lighthouse delegation against a real tenant.

**Infra-gated parts** (authored now, validated when infra lands): the deployed agent + Toolbox config + real
streaming; the marketplace publish + Lighthouse delegation; the #3199 live firing + the conditional middleware.

## Units (for the writing-plans handoff)

- `apps/hosted-platform/{Dockerfile,agent.yaml,main.py,requirements.txt}` — the Invocations full-parity agent.
- `azure.yaml` — 3rd `azure.ai.agent` service.
- `app/services/hosted.py` — real `stream_platform_agui` (AG-UI passthrough).
- `app/agents/per_request.py` (+ name/description override) & `app/agents/platform.py` (proxy via generic;
  delete `PerRequestPlatformAgent`).
- `app/core/tenant.py` (`TIER_DOMAINS`) & `app/api/tenant.py` (`onboard` accepts `tier`, seeds from map).
- `infra/managed-app/{*.bicep, mainTemplate.json, createUiDefinition.json, build.sh}`,
  `infra/lighthouse/{template, params}`.
- `docs/` — the marketplace-publish + Lighthouse-onboarding runbook.
- `apps/backend/eval/` — `tier_domains_test`, `per_request_override_test`, `hosted_platform_smoke_test` (+ the
  infra-gated `platform_hosted_e2e` expanded); possibly `app/agents/mcp/` middleware (the conditional #3199 fallback).

## Open questions (for the plan)

**Phase 1 step-0 verification checklist (gating precondition for ANY Phase 1 coding — rule #1, don't invent):**
1. **`InvocationsHostServer` signature** — the exact import + constructor in the installed
   `agent_framework_foundry_hosting`, **and whether the existing AG-UI platform agent (`build_platform_agent`)
   drops straight in** unchanged (the single most load-bearing integration point).
2. **Foundry Toolbox config surface** — how `build_hosted_from_connections`'s output maps to Toolbox MCP
   configuration + how OAuth identity passthrough is declared per connection (verify against the Toolbox /
   mcp-authentication docs + SDK before relying).
3. **ARM-TTK availability locally** — if `Test-AzTemplate`/pwsh isn't present, the structural lint is a
   documented manual gate, not an automated test.
4. **#3199 status** in the installed `agent-framework` — determines whether the middleware fallback is needed.
