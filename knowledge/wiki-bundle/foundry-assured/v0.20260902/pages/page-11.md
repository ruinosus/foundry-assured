---
type: service
title: Platform Ops Domain
description: "Tool-driven platform concierge over Microsoft MCP servers, including per-request tool assembly, role filtering, approval middleware, Foundry connection brokering, and hosted/live differences."
tags: [backend, platform, mcp, tools]
---
# Platform ops domain

`platform` is the backend’s tool-driven domain. Unlike grounded domains, it answers by assembling and calling MCP tools instead of retrieving corpus passages. The module docstring states the contract: tools are assembled per request from Microsoft first-party MCP servers, filtered by caller roles, and for OBO-capable servers run as the signed-in user. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/platform.py#L1-L9) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/platform.py#L25-L29)

## Runtime entrypoint

`build_platform_agent()` creates a `FoundryChatClient` bound to the current tenant config and current request credential, then turns it into an agent with `PLATFORM_INSTRUCTIONS`, MCP tools, and `ToolApprovalMiddleware`. The mounted runtime is not a static agent instance; the registry mounts `platform_agent_proxy`, a `PerRequestAgent` that rebuilds the platform agent on each run. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/platform.py#L50-L64) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/platform.py#L67-L76) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/registry.py#L183-L195)

The invariant is the same as helpdesk, but for tools: **never cache platform tools across requests**, because roles and credentials are caller-specific.

## Approval model

The domain uses the framework’s own `ToolApprovalMiddleware`, but with `auto_approval_rules=None`. The comment is explicit: nothing starts “on the loop”, and authorization stays earlier in tool construction, where unauthorized tools are filtered out before the agent sees them. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/platform.py#L31-L47)

That ordering is critical. Approval does not decide who may call a tool; it only pauses execution for tools the caller was already entitled to see.

## Tool assembly

`app/modules/platform_ops/internal/mcp_tools.py` is the canonical change surface for live MCP tooling. It supports two assembly paths:

- **Self-hosted/non-shared path**: iterate enabled registry servers and build `MCPStreamableHTTPTool` objects directly.
- **Shared path**: build tools from per-tenant `Connection` records and role-filtered visible tools.

[Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L82-L109) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L124-L181) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L184-L210) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L223-L240)

The step-by-step shared-mode flow is: resolve the current tenant’s `Connection` list, drop disabled or unknown kinds, map each connection to its registry server, tighten visible tools through `visible_tools_for(server, conn, roles)`, skip the server if no tools survive, resolve the final URL from connection data, then either build an internal `MCPStreamableHTTPTool` with a header provider or build a hosted tool by passing `project_connection_id` into `get_tool(...)`. This is where current tenant connections materially change tool availability. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L124-L181) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L184-L210) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L213-L240)

### Auth modes

The tool builder handles three auth patterns on the internal path:

- `public` → no auth header.
- `obo` → lazy per-call header provider minting a user bearer token.
- Foundry connection-backed secrets → lazy brokered header provider using `AIProjectClient.connections.get(..., include_credentials=True)`.

Non-OBO servers without a configured reference are skipped fail-closed. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L36-L68) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L92-L109) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L157-L175)

### Approval mode by tool class

For shared-mode connections, `_connection_build_params` assigns reads to `never_require_approval` and writes to `always_require_approval`. This is the central read/write approval contract for platform tools. The stricter-of-both RBAC rule comes from combining registry server metadata with per-connection min roles via `visible_tools_for`; if a tool cannot be classified or no allowed tools remain after tightening, the builder skips it fail-closed instead of exposing it optimistically. The hosted path then passes the same filtered tool set and approval map through `project_connection_id` rather than a live header provider. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L124-L147) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/platform_ops/internal/mcp_tools.py#L184-L210) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/platform_ops/mcp_registry_test.py#L1-L1) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/platform_ops/rbac_per_tool_test.py#L1-L1)

## Hosted path

The platform domain also has a hosted path, but it differs more than helpdesk’s hosted twin. The backend exposes `/platform-hosted`, and the hosted bridge uses an Invocations-style passthrough rather than the Responses re-encoding used for normal hosted agents. The bridge source carries explicit `TODO(infra-gated)` notes around auth scope, request body shape, and SSE framing, so some behavior is intentionally not considered fully verified offline yet. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/api.py#L29-L34) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L107-L118) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/internal/hosted.py#L121-L182)

## Representative tests

The platform domain has unusually rich focused tests:

- `tests/platform_ops/approval_mode_test.py`
- `tests/platform_ops/approval_parity_test.py`
- `tests/platform_ops/mcp_registry_test.py`
- `tests/platform_ops/mcp_brokering_e2e_test.py`
- `tests/platform_ops/platform_hosted_bridge_test.py` and hosted platform E2E/smoke tests

The MCP brokering E2E is especially important because it proves live Foundry connection credential fetch and OBO minting, two behaviors that unit tests cannot fully fake. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/platform_ops/mcp_brokering_e2e_test.py#L1-L20) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/platform_ops/mcp_brokering_e2e_test.py#L154-L187) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/platform_ops/mcp_brokering_e2e_test.py#L192-L241)
