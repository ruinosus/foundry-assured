# ADR-009 — Native tool-approval + Foundry-connection credential resolution (no self-read Key Vault, no hand-rolled HITL)

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [Sub-project C](../superpowers/specs/2026-06-29-subproject-c-credential-brokering-design.md) · builds on [ADR-005](./ADR-005-never-store-secrets.md), [ADR-008](./ADR-008-foundry-connections-app-configuration.md)

## Context

Sub-project C brokers credentials for the platform agent's MCP tools and gates write tools with
human approval. An early design had us **read the customer's Key Vault secret ourselves and inject
it as a header** (the `keyvault_ref` path) and **wrap the platform agent in a custom workflow** to
get a write-approval step. Researching against Microsoft showed both **reinvent first-party
mechanisms** — the same lesson as ADR-008.

## Decision

Use the Microsoft-native mechanisms; build neither a secret reader nor a custom HITL.

- **Credential resolution → Foundry connections + OBO; we never read a Key Vault secret.**
  - **OBO** (Microsoft-audience servers: Azure, Azure DevOps, Entra) — mint the user's
    On-Behalf-Of token on the internal path. No reference, no stored secret.
  - **Foundry connection** (everything non-OBO, e.g. GitHub) — the credential lives in a Foundry
    connection (ApiKey / Key Vault / Entra), referenced by `Connection.foundry_connection_id`.
    *Hosted path:* `get_mcp_tool(project_connection_id=...)` — Foundry resolves it. *Internal path:*
    retrieve the connection's credential via `azure-ai-projects` **at runtime** (Foundry is the
    store; we broker in memory, never persist). Microsoft: *"your agent definition never contains
    the actual secret values — only template references… the platform resolves them."*
  - **`keyvault_ref` is dropped** (it implied we read the Key Vault) in favor of
    `foundry_connection_id`. No `azure-keyvault-secrets` dependency.
- **Write approval → the framework's native tool-approval, not a custom workflow.**
  Set per-tool `approval_mode="always_require"` on write tools; the framework pauses and emits a
  `RequestInfoEvent` carrying `ToolApprovalRequestContent`. The existing CopilotKit approval card
  (already used for `create_ticket`) renders it; approval requires the **Approver/Admin** role
  (project rule #5). The AG-UI bug agent-framework #3199 (always_require not executing over AG-UI)
  is a **verification item** — confirm it's fixed in the installed version; if not, the fallback is
  a framework `RequestInfoEvent`-emitting middleware, still not a hand-rolled workflow.

## Consequences

- **+** We never read or store a customer secret — the secret boundary ([ADR-005](./ADR-005-never-store-secrets.md)) holds at runtime, not just at rest.
- **+** Much less custom code: no KV client, no `azure-keyvault-secrets`, no custom approval workflow — the framework + Foundry provide both.
- **+** Aligned with the Microsoft macro (Foundry connections as identity broker + native tool-approval HITL).
- **−** Non-OBO services on the **internal** path depend on `azure-ai-projects` exposing a get-connection-with-credentials call (verify the signature; don't invent it). If unavailable, non-OBO is hosted-only.
- **−** The write-approval over AG-UI depends on #3199 being fixed (or the middleware fallback).

## Alternatives considered

- **Self-read Key Vault + inject header** — makes us a secret handler, reinvents Foundry connections; rejected.
- **Custom workflow-as-agent with a `request_info` approval node** — reinvents the native tool-approval; rejected.

## Source (Microsoft guidance)

- [Using function tools with human-in-the-loop approvals (agent-framework)](https://learn.microsoft.com/agent-framework/agents/tools/tool-approval)
- [Human-in-the-loop in agent-framework workflows](https://learn.microsoft.com/agent-framework/workflows/human-in-the-loop)
- [Set up an Azure Key Vault connection (Foundry)](https://learn.microsoft.com/azure/ai-foundry/how-to/set-up-key-vault-connection)
- [Authentication and authorization in Foundry — connections as identity brokers](https://learn.microsoft.com/azure/foundry/concepts/authentication-authorization-foundry)
