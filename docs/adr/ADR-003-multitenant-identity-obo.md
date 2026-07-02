# ADR-003 — Identity: multi-tenant Entra app, tenant from `tid`, OBO downstream

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [SaaS target architecture](../superpowers/specs/2026-06-29-saas-target-architecture-design.md)

## Context

Today the backend is a single-tenant Entra app (`entra_tenant_id` is one fixed tenant) using
On-Behalf-Of (`OnBehalfOfCredential`) to act as the user against Foundry/Search. The SaaS model
must accept sign-ins from *any* customer tenant and act as each user against *their* resources.

## Decision

- Convert the API/SPA app registrations to **multitenant** ("accounts in any organizational directory").
- **Resolve the tenant from the token's `tid` claim**, and validate the `iss` matches the
  per-tenant issuer (multitenant token validation) — not just signature.
- Keep **OBO** as the runtime mechanism for Microsoft-audience downstreams (the customer's
  Foundry, Azure DevOps): exchange the user's token for a downstream token so we act *as the
  user*, scoped to the customer's tenant. Third-party (GitHub) uses OAuth passthrough
  ([ADR-005](./ADR-005-never-store-secrets.md)).
- **Onboarding = admin consent** of the multitenant app, which provisions our service principal
  in the customer tenant.

## Consequences

- **+** Reuses the existing OBO machinery (`app/core/auth.py`) — incremental, not a rewrite.
- **+** Per-user, per-tenant identity with no shared service account.
- **−** Token validation gains required `tid`/`iss` checks and an allowed-tenant list; a missing check is a cross-tenant risk.
- **−** Guest/personal-account edge cases need explicit handling (already partially present).

## Alternatives considered

- **One app registration per customer tenant** — strong isolation but unmanageable at scale; rejected.
- **Shared service identity (no OBO)** — loses per-user identity and the "acts as the user" property; rejected.

## Source (Microsoft guidance)

- [Convert single-tenant app to multitenant](https://learn.microsoft.com/entra/identity-platform/howto-convert-app-to-be-multi-tenant)
- [Architectural approaches for identity in multitenant solutions](https://learn.microsoft.com/azure/architecture/guide/multitenant/approaches/identity)
