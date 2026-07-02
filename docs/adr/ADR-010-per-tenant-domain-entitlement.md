# ADR-010 — Per-tenant domain enablement = license entitlement (not a feature flag)

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [Sub-project D-runtime](../superpowers/specs/2026-06-29-subproject-d-runtime-design.md) · builds on [ADR-001](./ADR-001-tenancy-deployment-stamps.md), [ADR-006](./ADR-006-tenant-scoped-config.md), [ADR-007](./ADR-007-coexistence-deployment-mode.md)

## Context

In shared mode the platform exposes several agent domains (`helpdesk`, `cockpit`, `selfwiki`,
`platform`). A tenant should only reach the domains it is entitled to — naturally tied to its
pricing `tier` (the `TenantRecord` already carries `tier`). The question is **how** to model and
store that per-tenant enablement: a feature-flag service (e.g. Azure App Configuration targeting
filters), or a stored entitlement on the tenant record.

An early design leaned toward feature flags. Researching against Microsoft's guidance showed that is
the **wrong tool for this job** — the same "don't reinvent / use the right first-party mechanism"
lesson as ADR-008/009, but here pointing *away* from a service rather than toward one.

## Decision

Model per-tenant domain enablement as a **license entitlement** stored on the tenant record, **not**
as a feature flag.

- **`TenantRecord.enabled_domains: tuple[str, ...]`** is the per-tenant entitlement — the set of
  domains the tenant may use. It is **data in the control-plane tenant catalog** (ADR-001's
  "tenant list as data"), read at request time by a `require_domain(domain_id)` gate. Fail-closed:
  no record / domain not in the set → 403.
- The entitlement is **tier-adjacent**: onboarding seeds `enabled_domains` (MVP default: all
  registered domains; a tier→domain-set mapping can drive the default later without schema change),
  and an Admin can tighten it per tenant via the management API/UI.
- **Azure App Configuration feature flags remain the right tool for a *different* concern** —
  progressively rolling out *new* features/versions across tenants — and are **out of scope for D**.
  We do not conflate "is this tenant licensed for this domain" (entitlement) with "is this new
  feature turned on yet" (flag).

Microsoft, verbatim:
> "Feature flags aren't usually the right choice for these scenarios… Instead, consider building a
> process to track and enforce the **license entitlements** that each customer has." …
> "use different pricing tiers with license entitlements to selectively enable features for tenants
> that require them."

## Consequences

- **+** The enablement check is a cheap, synchronous, fail-closed read of data we already hold (the
  tenant catalog) — no extra service dependency, no eventual-consistency window, aligned with
  ADR-001/006/007.
- **+** Entitlement is auditable and tenant-scoped by construction (`current_tenant_id()` only,
  never a path tid), consistent with the rest of the SaaS seam.
- **+** Leaves App Configuration feature flags available, unconfused, for progressive rollout later.
- **−** No built-in percentage/targeting rollout semantics (those are a feature-flag concern we
  deliberately don't need here). If we later want gradual *feature* rollout, that's a separate
  mechanism, not this field.

## Migration note (operational)

`enabled_domains` defaults to `()` and the `require_domain` gate is fail-closed. A tenant onboarded
**after** D-runtime is seeded with all domains (`enabled_domains=DOMAIN_IDS`). But a tenant whose
record was written **before** this change deserializes with `enabled_domains=()` — so in shared mode
that tenant gets a **403 on every domain until an Admin grants domains** via `PUT /tenant/domains`.
This is the intended fail-closed direction, not a bug: when migrating an existing shared deployment,
backfill `enabled_domains` for pre-existing tenants (or expect their first post-deploy requests to
403) so the 403s aren't mistaken for a regression.

## Alternatives considered

- **Azure App Configuration feature flags + targeting filter (per-tenant audience)** — the
  documented tool for *progressive feature rollout*, explicitly **not** recommended for licensing /
  entitlement; adds a service dependency and an eventual-consistency window for a decision that is
  really catalog data. Rejected for entitlement; reserved for future progressive rollout.
- **Hard-code domain availability by `tier` in code** — reinvents per-tenant specialization in the
  codebase (the antipattern Microsoft calls out); not overridable per tenant. Rejected.

## Source (Microsoft guidance)

- [Architectural approaches for deployment and configuration of multitenant solutions — Feature flags / license entitlements + the "specialized customizations for tenants" antipattern](https://learn.microsoft.com/azure/architecture/guide/multitenant/approaches/deployment-configuration)
- [Considerations for updating a multitenant solution — Feature flags](https://learn.microsoft.com/azure/architecture/guide/multitenant/considerations/updates)
- [Azure App Configuration considerations for multitenancy](https://learn.microsoft.com/azure/architecture/guide/multitenant/service/app-configuration)
