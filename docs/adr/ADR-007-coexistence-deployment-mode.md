# ADR-007 — Coexistence via a deployment-mode seam (one codebase, three modes)

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [SaaS target architecture](../superpowers/specs/2026-06-29-saas-target-architecture-design.md)

## Context

The self-hosted product must keep working unchanged while we add the managed (shared) and
dedicated stamps. We do not want a fork: divergent codebases double the maintenance and let the
self-hosted path rot.

## Decision

Introduce a single point of variation — **`DEPLOYMENT_MODE`** (env) selecting a
**`TenantConfigProvider`** implementation at boot:

| Mode | Provider | Tenancy | Runs where |
|---|---|---|---|
| `self_hosted` (today) | `SingleTenantConfigProvider` → the current global `settings` | 1 | customer cloud, customer operates |
| `dedicated` (enterprise) | `SingleTenantConfigProvider` (same) inside a Managed App | 1 | customer cloud, we operate |
| `shared` (SMB/default) | `MultiTenantConfigProvider` → resolves config by `tid` from the store | N | our cloud |

All other code (workflow, agents, RBAC, assurance gates) asks the provider for "the current
tenant's config" and is **identical across modes** — it never knows which mode is running.

**Migration discipline:** ship the provider with the `SingleTenant` implementation **first**,
routing all `settings` access through it with **zero behavior change** (existing eval tests stay
green), *before* adding `MultiTenant`. This de-risks the auth/config refactor.

## Consequences

- **+** No fork; the self-hosted product is a configuration of the same code.
- **+** The risky multi-tenant change is isolated behind one seam and introduced incrementally.
- **−** Every `settings` access must move behind the provider (mechanical but broad — see [ADR-006](./ADR-006-tenant-scoped-config.md)).
- **−** Mode-specific behavior must be kept out of the core and confined to the provider/packaging.

## Alternatives considered

- **Separate branches/repos per mode** — diverges and rots; rejected.
- **Runtime feature flags scattered in code** — untestable and leaky; rejected in favor of one provider seam.

## Source (Microsoft guidance)

- [Architectural approaches for deployment and configuration of multitenant solutions](https://learn.microsoft.com/azure/architecture/guide/multitenant/approaches/deployment-configuration)
- [SaaS and multitenant solution architecture](https://learn.microsoft.com/azure/architecture/guide/saas-multitenant-solution-architecture/)
