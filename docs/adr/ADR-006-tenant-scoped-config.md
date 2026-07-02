# ADR-006 — Tenant-scoped config and isolation (replace the global `settings`)

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [SaaS target architecture](../superpowers/specs/2026-06-29-saas-target-architecture-design.md)

## Context

Today `settings = Settings()` is a single global loaded from `.env`, and `memory_scope()`
namespaces memory by user (`user.oid`) but not by tenant. In a multi-tenant control plane,
configuration and every data access must be scoped to the current tenant — Microsoft calls
tenant-scoping in the data layer "the most important security consideration" for multitenant
SaaS.

## Decision

- Replace direct use of the global `settings` with a **`TenantConfigProvider.current()`** that
  returns the **current tenant's** config (data-plane pointers + enabled connections + enabled
  domains). See [ADR-007](./ADR-007-coexistence-deployment-mode.md) for the provider implementations.
- **Namespace memory and any tenant-owned state by tenant**, e.g. `memory_scope()` becomes
  `f"{tid}:{user.oid}"` **in the `MultiTenant` impl only**. The `SingleTenant` impl keeps the
  existing **un-prefixed** `user.oid` scope — memory keys are *persisted state*, so prefixing them
  in the self-hosted path would orphan existing memories. The "zero behavior change" guarantee
  ([ADR-007](./ADR-007-coexistence-deployment-mode.md)) therefore covers persisted memory, not
  just config reads.
- Enforce tenant scoping at a **single choke point** (the provider / store access layer), not
  sprinkled through call sites, so it is auditable.
- The static MCP server registry becomes the **catalog/shape**; the *enabled* connections and
  endpoints come from the per-tenant store.

## Consequences

- **+** Cross-tenant leakage is preventable and auditable at one layer.
- **+** The per-tenant config model ([fig 4](../diagrams/saas/04-tenant-config-model.mmd)) is the single source of per-tenant truth.
- **−** Broad refactor: every current read of `settings.<x>` must route through the provider.
- **−** Tests must cover the tenant-scoping invariant explicitly (a missing scope is a security bug, not a functional one).

## Alternatives considered

- **Per-tenant process/instance (no in-code scoping)** — that's the dedicated stamp; for the shared stamp we still need in-code scoping, so this is complementary, not a substitute.

## Source (Microsoft guidance)

- [Architectural considerations for identity in a multitenant solution](https://learn.microsoft.com/azure/architecture/guide/multitenant/considerations/identity)
- [Multitenancy checklist on Azure](https://learn.microsoft.com/azure/architecture/guide/multitenant/checklist)
