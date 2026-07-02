# ADR-008 — Use Foundry connections + Azure App Configuration + Key Vault, not a custom credential store

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [SaaS target architecture](../superpowers/specs/2026-06-29-saas-target-architecture-design.md) · [Sub-project B](../superpowers/specs/2026-06-29-subproject-b-connections-design.md)

## Context

Sub-project B manages, per tenant, the data-plane pointers (Foundry/Search) and the connections
to external services (GitHub, Azure DevOps, …). An early design had B store each connection's
`auth_method` + `secret_ref` in our own store and (later) run the OAuth flow itself. Researching
against Microsoft showed this **reinvents two first-party services** and would make us a
credential store — contradicting [ADR-005](./ADR-005-never-store-secrets.md).

## Decision

Lean on the Microsoft-native services instead of building our own:

- **External-service auth → Foundry project connections.** Foundry connections are *identity
  brokers* that authenticate to external systems (Microsoft and non-Microsoft) on behalf of
  project users, via managed identity / service principal; "store shared credentials in a project
  connection instead of passing them at runtime." Our `Connection` entity holds a
  **`foundry_connection_id`** (a reference), never the credential. Foundry handles the OAuth /
  token brokering.
- **Per-tenant configuration → Azure App Configuration** is the idiomatic backend (tenant-id as
  key prefix; global settings in a shared store; native Key Vault references). The
  `TenantStore` interface from [ADR-006](./ADR-006-tenant-scoped-config.md)/sub-project A stays;
  B's first impl is **Azure Table Storage (cheapest)**, swappable to App Configuration with no
  schema change.
- **Secrets → Azure Key Vault**, per tenant (separate vault) or `tid`-prefixed secret names;
  referenced by `keyvault_ref`, never stored by us.

So B stores **references and governance metadata** (kind, min-role, enabled, `foundry_connection_id`
/ `keyvault_ref`) — not credentials, and runs **no OAuth flow** (Foundry connections / sub-project
C do the brokering).

## Consequences

- **+** We are not a credential store; the secret boundary ([ADR-005](./ADR-005-never-store-secrets.md)) is enforced by design — the schema has no secret field, the UI physically can't take one.
- **+** Less to build: no OAuth dance, no token storage — Foundry connections + Key Vault provide them.
- **+** Aligned with the macro architecture Microsoft indicates for multitenant SaaS (App Configuration + Key Vault + Foundry connections).
- **−** Runtime brokering depends on Foundry connections existing in the customer's project (created in the Foundry portal / via SDK) — an onboarding step the customer (or sub-project C) performs.
- **−** App Configuration as the production config backend is a future swap (B ships Table Storage); the interface makes it cheap, but the migration is real work when it happens.

## Alternatives considered

- **Custom Connection store with `secret_ref` + our own OAuth flow** — reinvents Foundry connections + App Configuration, makes us a credential store, contradicts ADR-005; rejected.
- **Store secrets encrypted in our store** — same breach/ownership problem; rejected.

## Source (Microsoft guidance)

- [Authentication and authorization in Foundry — connections as identity brokers](https://learn.microsoft.com/azure/foundry/concepts/authentication-authorization-foundry)
- [Add a connection to your Foundry project](https://learn.microsoft.com/azure/ai-foundry/how-to/connections-add)
- [Azure App Configuration considerations for multitenancy](https://learn.microsoft.com/azure/architecture/guide/multitenant/service/app-configuration)
- [Use Azure Key Vault in a multitenant solution](https://learn.microsoft.com/azure/architecture/guide/multitenant/service/key-vault)
