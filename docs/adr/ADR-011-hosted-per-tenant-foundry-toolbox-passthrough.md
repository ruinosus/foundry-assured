# ADR-011 — Hosted per-tenant tool resolution via Foundry Toolbox + OAuth identity passthrough

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [Sub-project D-packaging](../superpowers/specs/2026-06-29-subproject-d-packaging-design.md) · refines [ADR-009](./ADR-009-native-tool-approval-foundry-connection-resolution.md) for the hosted path

## Context

D-runtime shipped the `/platform-hosted` twin as a clean-error skeleton: the route, the frontend
toggle, and the AG-UI envelope are real, but the *deployed* agent and its per-tenant tool resolution
were deferred. D-runtime chose the **Invocations** protocol for the twin (not Responses) because the
platform agent carries **write-approval HITL**, which Responses can't round-trip. D-packaging now
deploys that agent for real. The question: how does a *single deployed* hosted agent resolve **per-tenant**
tools and run them **as the signed-in user**, without the agent handling credentials itself?

An early instinct was to thread C's `build_hosted_from_connections` + a hand-rolled per-tenant
credential read into the container. Researching against Microsoft showed Foundry provides this as a
first-party mechanism — the same "don't reinvent" lesson as ADR-008/009/010.

## Decision

The deployed platform hosted agent resolves tools through the **Foundry Toolbox** MCP endpoint, with
**OAuth identity passthrough** for per-user/per-tenant execution. The agent never manages credentials.

- **Tools via the Foundry Toolbox MCP endpoint.** Hosted agents do not inject tools directly; they
  connect to a Toolbox MCP endpoint provisioned in the Foundry project, which *"centrally manages
  authentication"* across OAuth identity passthrough, Entra managed identity, and key-based. This is
  where C's `build_hosted_from_connections` lands — as Toolbox configuration, not in-container code.
- **Per-tenant identity = OAuth identity passthrough (OBO).** When the agent is invoked through a
  user-facing entry point (our AG-UI app, carrying the user token), the Toolbox propagates user
  context via OAuth 2.0 On-Behalf-Of to downstream tools — so tools run **as the signed-in user**,
  per-tenant, with consent gathered on first use. No stored secret; the agent definition holds only
  Toolbox references.
- **The container is protocol-only.** `apps/hosted-platform` uses `InvocationsHostServer`
  (`agent_framework_foundry_hosting`) to serve the **same AG-UI agent** we already run at `/platform`;
  Invocations lets the AG-UI event stream flow through Foundry **untouched** (so the write-approval
  interrupt survives end-to-end). Tool auth is the Toolbox's job, not the container's.

## Consequences

- **+** No stored/handled secret in the container; per-tenant identity is a first-party Foundry flow
  (consistent with ADR-005/008/009 — the secret boundary holds at runtime on the hosted path too).
- **+** The hosted twin reuses the existing AG-UI agent verbatim (Invocations passes AG-UI untouched),
  so the write-approval HITL the twin exists for survives without re-implementation.
- **+** Aligned with the Microsoft macro (Toolbox as the central tool-auth broker; OBO passthrough for
  per-user).
- **−** OAuth identity passthrough is preview and has reported rough edges (Microsoft Q&A: "MCP tool
  with OAuth Identity Passthrough fails to call MCP tool after auth"). The per-tenant tool path is
  **infra-gated** — authored now, validated live against a deployed agent + Toolbox; the consent-link
  first-use flow must be exercised with a real user.
- **−** Requires a Toolbox provisioned per Foundry project (a deploy-time step, part of D-packaging's
  infra-gated runbook).

## Alternatives considered

- **Read per-tenant connection credentials in the container and inject headers** — reinvents the
  Toolbox / Foundry connections broker and makes the container a secret handler; rejected (same as
  ADR-009's rejected self-read-Key-Vault).
- **A Responses-protocol single-identity hosted agent (like helpdesk-concierge)** — simpler, but drops
  the write-approval HITL that is the entire reason the twin uses Invocations; rejected.

## Source (Microsoft guidance)

- [Curate intent-based toolbox in Foundry (preview)](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/toolbox)
- [Set up MCP server authentication (OAuth identity passthrough / Entra / key)](https://learn.microsoft.com/azure/foundry/agents/how-to/mcp-authentication)
- [Connect to MCP server endpoints for agents](https://learn.microsoft.com/azure/foundry/agents/how-to/tools/model-context-protocol)
- [Hosted agents — protocols (Invocations for AG-UI)](https://learn.microsoft.com/azure/foundry/agents/concepts/hosted-agents)
- [Foundry hosted agents (agent-framework hosting — InvocationsHostServer)](https://learn.microsoft.com/agent-framework/hosting/foundry-hosted-agent)
