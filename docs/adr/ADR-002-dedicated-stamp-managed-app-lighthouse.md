# ADR-002 — Dedicated stamp = Managed Application; cross-tenant data-plane management = Lighthouse

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [SaaS target architecture](../superpowers/specs/2026-06-29-saas-target-architecture-design.md)

## Context

The hybrid model ([ADR-001](./ADR-001-tenancy-deployment-stamps.md)) needs two delivery
vehicles: one to put a **dedicated control plane into the customer's subscription**
(enterprise), and one to let us **manage the customer's data-plane resources** from our tenant
in the shared model — without ever owning the customer's data.

## Decision

- **Dedicated stamp → Azure Managed Application.** We publish the control plane as a managed
  application; it deploys into a resource group in the *customer's* subscription that the
  customer cannot directly modify, while we (the publisher) operate it. "Everything is the
  customer's," including the control plane, with us as operator.
- **Shared-model data-plane management → Azure Lighthouse.** The customer delegates specific
  subscriptions/resource groups to us; we manage those delegated resources cross-tenant from
  our own tenant, and the customer keeps full visibility and can revoke at any time.

## Consequences

- **+** Both Microsoft-sanctioned, marketplace-publishable, with clear ownership boundaries.
- **+** Lighthouse delegation is revocable and auditable by the customer — fits "we orchestrate, they own."
- **−** Managed Application packaging is extra build/release work (a separate artifact + marketplace offer).
- **−** Lighthouse delegation scope must be least-privilege and reviewed; over-delegation is a risk.

## Implementation note (D-packaging)

The Managed App's marketplace artifacts are authored in **Bicep that composes the existing `infra/`
modules** (`resources.bicep`, `containerapps.bicep`) and compiled to the required root
`mainTemplate.json` (ARM JSON) via `bicep build` — so the dedicated-stamp template is a
customer-subscription re-parameterization of the same resources, not a duplicate. Structurally
validated offline (`bicep build` + ARM-TTK + the createUiDefinition sandbox); marketplace publish +
real-tenant Lighthouse delegation are infra-gated. See
[sub-project D-packaging](../superpowers/specs/2026-06-29-subproject-d-packaging-design.md).

## Alternatives considered

- **Service principal with broad rights in the customer tenant** — simpler but opaque and hard to revoke; rejected for the auditability Lighthouse gives.
- **Customer-run scripts only** — that's the self-hosted path; doesn't deliver a *managed* enterprise stamp.

## Source (Microsoft guidance)

- [Azure Lighthouse and Azure managed applications](https://learn.microsoft.com/azure/lighthouse/concepts/managed-applications)
- [Azure Lighthouse in ISV scenarios](https://learn.microsoft.com/azure/lighthouse/concepts/isv-scenarios)
