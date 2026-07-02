# ADR-005 — The control plane never stores customer secrets

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [SaaS target architecture](../superpowers/specs/2026-06-29-saas-target-architecture-design.md)

## Context

As the orchestrator we broker access to the customer's resources (Foundry, ADO, GitHub) on
every request. If we persisted customer secrets, we would become a high-value breach target and
inherit the customer's compliance burden — defeating the "everything is the customer's" thesis.

## Decision

The control-plane store holds **configuration and connection metadata only — never secrets and
never customer data.** Secrets are handled by reference and resolved at runtime:

- **Microsoft-audience downstream (Foundry, ADO):** no stored secret — **OBO** mints a per-user
  token at call time ([ADR-003](./ADR-003-multitenant-identity-obo.md)).
- **Third-party (GitHub):** **OAuth identity passthrough** — the third-party token is held by
  the customer's Foundry Agent Service; the control-plane store holds only a connection
  reference. (Canonical wording, reused verbatim in the spec §2 and Fig 2.)
- **Secrets at rest (when unavoidable):** in the **customer's Key Vault**, optionally with
  **customer-managed keys (CMK)** cross-tenant; a `Connection.secret_ref` points at the Key
  Vault URI / Foundry connection id — never the secret value.

Microsoft explicitly blocks passing a Microsoft-audience token to a third-party MCP endpoint
("Cannot pass Microsoft token to untrusted MCP endpoint"), so third-party connections must use
their own OAuth, not OBO.

## Consequences

- **+** We are not a secret store; breach blast-radius and compliance scope shrink dramatically.
- **+** Customers retain key custody and can revoke (Key Vault / consent) without our involvement.
- **−** Runtime token brokering adds latency and failure modes; every path must fail closed.
- **−** Requires custom-OAuth app registrations (audience we control) for hosted third-party passthrough.

## Alternatives considered

- **Encrypt-and-store customer secrets in our store** — simpler runtime, but makes us the breach target and owner of the secret; rejected.

## Source (Microsoft guidance)

- [Set up MCP server authentication (OAuth identity passthrough)](https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication)
- [Configure cross-tenant customer-managed keys](https://learn.microsoft.com/azure/storage/common/customer-managed-keys-configure-cross-tenant-existing-account)
