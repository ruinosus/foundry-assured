# Platform domain

The `platform` domain is the repository's tool-driven concierge. Unlike `helpdesk`, `cockpit`, and `selfwiki`, it does not primarily answer by retrieving a knowledge corpus. It answers by using connected Microsoft tools.

The backend's live surface is mounted at `POST /platform` when configured, and its hosted bridge is `POST /platform-hosted`.

## Ownership and entrypoints

The domain is assembled from these symbols:

- `DomainSpec(id="platform", kind="tool")` in [`apps/backend/app/domains.py`](../../apps/backend/app/domains.py)
- `domains._mount_platform()` for the live AG-UI path
- `app.agents.platform.platform_agent_proxy` and `platform_configured()` for the live runtime binding
- `services.hosted.stream_platform_agui()` for the hosted bridge path

The repository also carries MCP- and platform-focused tests in `apps/backend/eval/*platform*`, `*mcp*`, and RBAC-related test files.

## Live platform path

`_mount_platform()` only mounts the route when `platform_configured()` is true. That guard prevents exposing a broken tool domain in environments where MCP integration is not configured.

When mounted, the live endpoint uses `add_agent_framework_fastapi_endpoint(...)` with `platform_agent_proxy`.

### Why `platform_agent_proxy` matters

The source comment in `domains.py` explains that `platform_agent_proxy` is a `PerRequestAgent`. The agent is rebuilt on each run so tools can be filtered under:

- the caller's roles,
- the caller's OBO credential.

That makes the live platform path materially different from hosted tool execution. Live requests are caller-scoped, not just environment-scoped.

## Live tool assembly flow

The main live tool builder is `build_mcp_tools()` in `app/agents/mcp/tools.py`, and it is explicitly mode-aware.

### Self-hosted and dedicated modes

For any non-shared deployment mode, `build_mcp_tools()` keeps the registry-driven path:

- compute the caller roles with `current_roles()` or `{ "Admin" }` when auth is off,
- iterate `enabled_servers()` from `app/agents/mcp/registry.py`,
- call `_build_one(server, roles)` for each server,
- return only the non-`None` tools.

This path reads flat config such as ADO org or GitHub PAT from `tenant_config()` and skips servers whose required settings are absent.

### Shared mode

For `deployment_mode == "shared"`, `build_mcp_tools()` switches to tenant-scoped connection building:

- `_current_tenant_connections()` loads the current tenant record from the shared tenant store using `current_tenant_id()`,
- `build_from_connections(conns, roles)` iterates those `Connection` records,
- `_build_from_connection(conn, roles)` resolves each tool.

So shared mode externalizes live tool inventory into the tenant's stored connection set instead of relying on one process-wide registry configuration.

## RBAC and fail-closed classification

The registry in `app/agents/mcp/registry.py` is the source of truth for classification and minimum grants.

Important rules:

- `classify_tool(server, tool_name)` is fail-closed: any tool not explicitly listed in `read_tools` is treated as a write.
- `visible_tools(server, roles)` exposes registry reads only to callers satisfying `server.min_role` and writes only to callers satisfying `server.min_role_write`.
- `visible_tools_for(server, conn, roles)` is **stricter-of-both**: callers must satisfy both the registry's grant and the connection record's `min_role_read` or `min_role_write`.

That means tenant configuration can only tighten visibility, never loosen it beyond the registry's policy.

## Connection and server skip cases

`app/agents/mcp/tools.py` contains multiple fail-closed skip paths:

- disabled connections are ignored,
- unknown connection kinds are ignored,
- callers with no visible tools for a server get no tool,
- missing templated endpoint data such as ADO org yields no tool,
- missing PAT or missing non-OBO connection reference yields no tool,
- unsupported auth mode on the internal path yields no tool.

The result is that under-classified or under-configured tools disappear rather than partially working with overly broad access.

## Credential and approval parameterization

### Internal live tools

The internal path builds `MCPStreamableHTTPTool` instances with:

- `allowed_tools` filtered by role and classification,
- `approval_mode="never_require"` on the self-hosted registry path because live AG-UI uses the repository's own HITL mechanism rather than framework-native tool approval,
- a `header_provider` when auth is needed.

Auth shapes on the live internal path:

- **public**: no header provider,
- **OBO**: `_obo_header_provider(scope)` mints a fresh downstream bearer from `credential_for_request()` at call time,
- **non-OBO Foundry-backed**: `_foundry_connection_header_provider(connection_id)` fetches credentials from the tenant's Foundry connection at call time,
- **GitHub PAT**: `_static_header_provider(pat)` injects a fixed bearer.

### Connection-driven live tools

For shared-mode connection-backed tools, `_connection_build_params(...)` builds an `approval_mode` dict:

- `always_require_approval` for writes,
- `never_require_approval` for reads.

The connection-backed internal tool still uses header providers when the path is internal live execution.

### Hosted tools

`build_hosted_from_connections(conns, roles, get_tool)` is different. It does **not** pass header providers. Instead it calls `get_tool(...)` with:

- `name`
- `url`
- `allowed_tools`
- `approval_mode`
- `project_connection_id`

That means Foundry, not the backend process, resolves the credential from the referenced project connection.

## Hosted platform path

The backend bridge for the hosted twin is in [`apps/backend/app/services/hosted.py`](../../apps/backend/app/services/hosted.py).

- Route: `POST /platform-hosted`
- Dependency set: `_domain_deps("platform")`
- Bridge function: `stream_platform_agui(body)`

Unlike `stream_agui()` for Responses-based hosted agents, `stream_platform_agui()` is designed around the **Invocations** protocol because the hosted platform path is supposed to support AG-UI-style write-approval interrupts.

## Why platform is different from grounded domains

| Domain family | Primary mechanism | Main backend seam |
| --- | --- | --- |
| Helpdesk | workflow over LLM agents and KB | `app/workflow/*` |
| Cockpit and selfwiki | retrieve then synthesize from docs | `services/grounded.py` and `services/retrieval.py` |
| Platform | per-request tool use | `app.agents.platform`, MCP/tool wiring, hosted Invocations bridge |

This distinction matters when changing prompts, auth, or validation. Platform behavior is often more about tool inventory and approval semantics than about citation retrieval.

## Approval-aware write behavior

The repository-level product contract says the platform domain requires human approval for write actions. In the live path, this is why per-request tool building and caller-scoped roles matter.

The hosted path encodes the same design intent in comments inside `apps/hosted-platform/main.py`:

- use Invocations, not Responses,
- preserve write-approval interrupts,
- keep tool capability rather than stripping it down to pure Q&A.

The backend bridge reflects this by trying to pass through AG-UI SSE rather than re-encoding a simple response stream.

## Current evidence-backed limitations

`stream_platform_agui()` contains several clearly marked infra-gated TODOs that are part of the current design surface:

1. the exact Foundry data-plane scope for hosted platform Invocations is based on best evidence rather than an offline-verified SDK constant,
2. the exact request body shape expected by the hosted Invocations endpoint is not fully verified offline,
3. the SSE passthrough likely needs `aiter_bytes()` rather than `aiter_lines()` to avoid losing event separators.

These TODOs are not generic cleanup items. They are part of the current architectural truth: hosted platform parity is intended, but some aspects are only fully knowable against deployed infrastructure.

## Configuration boundaries

Global platform-related switches live in `PlatformSettings`:

- `mcp_enabled`
- `mcp_learn_url`

Per-tenant MCP-related data belongs in `TenantConfig` and tenant connection records, not in hard-coded runtime branches. This matches the repository rule that access and environment variance should be data-driven.

The newer shared-mode design prefers per-tenant `Connection` records over legacy flat config fields like `mcp_github_pat`. Those legacy fields remain for backward compatibility in self-hosted mode but are not the preferred extensibility surface.

## Tests that define the platform domain

Representative backend tests include:

- `mcp_registry_test.py`: MCP registry behavior, including disabled servers and unclassified-tool fail-closed behavior.
- `mcp_connect_test.py`: connection logic.
- `mcp_brokering_e2e_test.py`: end-to-end brokering behavior.
- `mcp_learn_test.py`: Learn tool path.
- `connection_ops_test.py`, `connection_store_test.py`, `connection_tools_build_test.py`: tenant connection and tool-building behavior, including disabled, unknown-kind, missing-URL, and no-role skip cases.
- `rbac_per_tool_test.py`: per-tool RBAC tightening between registry grants and per-connection thresholds.
- `hosted_build_test.py`: hosted build parameterization such as `project_connection_id` and approval dicts.
- `platform_hosted_bridge_test.py`: hosted bridge shape.
- `platform_hosted_e2e_test.py` and `hosted_platform_smoke_test.py`: hosted platform expectations.

## Validation

From `apps/backend/`:

```bash
uv run pytest eval/mcp_registry_test.py eval/mcp_connect_test.py eval/connection_tools_build_test.py eval/rbac_per_tool_test.py eval/platform_hosted_bridge_test.py eval/hosted_build_test.py
```

## Related pages

- Backend auth and tenancy
- Admin and tenant APIs
- Hosted platform
- Automation and release
