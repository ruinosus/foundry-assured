---
title: Explanation
description: Understanding-oriented — the ADRs, the multi-tenant SaaS model, the DNA prompt integration, and the case studies.
type: explanation
audience: evaluator
status: stable
updated: 2026-07-11
---

# Explanation

Understanding-oriented material — the *why* behind the decisions, and the evidence that the
mechanism generalizes.

## Architecture decisions

Every significant decision is an [ADR](../adr/README.md) (context → decision → consequences,
MADR-style, grounded in the Microsoft guidance it follows). The full index (001–014) covers
tenancy, identity, secret handling, the deployment-mode seam, domain entitlement, the deep-wiki
reuse, and the declarative-prompt integration.

## The multi-tenant SaaS model

The repo is a **hybrid multi-tenant SaaS** — one codebase, three deployment modes, selected by a
**deployment-mode seam** ([ADR-007](../adr/ADR-007-coexistence-deployment-mode.md)). A
`TenantConfigProvider` (Single/Multi implementation) is the single point of variation; everything
else is identical across modes.

| Mode | Tenancy | Where | Vehicle |
|---|---|---|---|
| **self_hosted** (today, default) | 1 | customer cloud, customer operates | `azd up` |
| **dedicated** (enterprise) | 1 | customer cloud, we operate | Azure **Managed Application** + **Lighthouse** |
| **shared** (SMB / default SaaS) | N | our cloud | multi-tenant control plane; tenant resolved per-request from the Entra `tid` |

All data, compute, and credentials stay in the customer's cloud (BYO) — the control plane stores
**per-tenant config + connection references only, never secrets, never customer data**
([ADR-005](../adr/ADR-005-never-store-secrets.md)). In **shared** mode each request resolves its
tenant from the token's `tid`, loads that tenant's config + `Connection` records, mints a brokered
token (OBO for Microsoft-audience servers; OAuth identity passthrough / Foundry connections
otherwise), and calls the customer's own data plane. Design detail: the
[SaaS target architecture spec](../superpowers/specs/2026-06-29-saas-target-architecture-design.md)
and ADRs [001](../adr/ADR-001-tenancy-deployment-stamps.md)–[011](../adr/ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md).

## The DNA prompt integration

Agent instructions moved from inline Python strings to a **declarative DNA scope**
([ADR-013](../adr/ADR-013-declarative-agent-prompts-dna.md)), and the runtime prompt scope
**decouples from the image** so prompt edits are a restart, not a rebuild
([ADR-014](../adr/ADR-014-runtime-prompt-scope-no-rebuild.md)). This is *why* the
[`.dna` scopes](../reference/dna-scopes.md) exist and why prompt changes are gated by an eval suite
rather than a byte-equivalence check.

## The measured case studies

The assurance mechanism is domain-agnostic; these are the proofs.

- **[Use-case walkthrough](../USE-CASE-WALKTHROUGH.md)** — a worked, fictional example of the whole
  mechanism end to end.
- **[Case study: the LLM wiki loop](../CASE-STUDY-LLM-WIKI-LOOP.md)** — a measured
  generate→verify→ingest→consume loop for grounding an agent on a large codebase.
- **[Case study: self-wiki dogfood](../CASE-STUDY-SELFWIKI-DOGFOOD.md)** — dogfooding the mechanism
  on this repo: two bugs it found in itself, and the genericity proof.
- **[Microsoft alignment](../MICROSOFT-ALIGNMENT.md)** — how the design tracks Microsoft's own
  guidance and patterns.

## The living plans

Design rationale and intended work (conceptual, tracked): the
[assurance mechanism plan](../ASSURANCE-MECHANISM-PLAN.md), the
[RBAC & user-management plan](../RBAC-AND-USER-MANAGEMENT-PLAN.md), the
[second-domain wiki plan](../SECOND-DOMAIN-WIKI-PLAN.md), and the
[MCP integration plan](../MCP-INTEGRATION-PLAN.md).
