---
type: implementation-guide
title: Platform per-request agent proxy
description: How the platform domain uses PerRequestAgent to satisfy AG-UI serving requirements while rebuilding caller-specific tools, tenant config, and OBO credentials on each request.
tags: [backend, platform, per-request, agents]
---

The platform domain cannot be served by one eagerly built agent instance in the same way as ordinary single-tenant agents. Its tool set and credential context are caller-specific, and in shared mode even `tenant_config()` is unavailable until request auth resolves the current tenant. `PerRequestAgent` exists to satisfy the AG-UI adapter’s requirement for an agent instance while still rebuilding the real inner agent on every delegated call.[`apps/backend/app/agents/per_request.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/per_request.py#L1-L16) [`apps/backend/app/agents/platform.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/platform.py#L1-L10)

## Why eager construction is insufficient

A plain agent built at import or mount time would bake in the wrong state for two reasons:

- in shared mode, no tenant has been resolved yet, so `tenant_config()` cannot safely supply request-specific config.[`apps/backend/app/agents/per_request.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/per_request.py#L3-L8)
- platform tools are filtered by the current caller’s roles and may require an OBO credential for downstream servers, so tool assembly must happen after auth dependencies have populated request context.[`apps/backend/app/agents/platform.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/platform.py#L31-L44) [`apps/backend/app/agents/mcp/tools.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/mcp/tools.py#L223-L240)

By contrast, the ordinary workflow client helper `_client()` can eagerly read `tenant_config()` because its agents are constructed inside request-bound workflow builders, not at app mount time.[`apps/backend/app/workflow/agents.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/workflow/agents.py#L25-L31)

## How PerRequestAgent satisfies the protocol

`PerRequestAgent` is a generic proxy that carries stable `id`, `name`, and `description` attributes and delegates `run`, `create_session`, and `get_session` by calling `self._builder()` each time. That is enough to satisfy the runtime-checkable `SupportsAgentRun` protocol expected by the AG-UI adapter.[`apps/backend/app/agents/per_request.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/per_request.py#L10-L16) [`apps/backend/app/agents/per_request.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/per_request.py#L25-L48)

The AG-UI adapter gets one stable instance; each request gets a freshly built underlying agent.

## Platform-specific export

`platform_agent_proxy` is the exported serving object used by route mounting. It wraps `build_platform_agent()` and overrides the default proxy `name` and `description` so the platform identity is advertised consistently even though the inner agent is rebuilt per call.[`apps/backend/app/agents/platform.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/platform.py#L47-L56) [`apps/backend/app/domains.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/domains.py#L152-L165)

## Cosmetic defaults versus runtime-derived behavior

`PerRequestAgent` deliberately separates cosmetic metadata from runtime behavior:

- `id`, `name`, and `description` are stable proxy attributes
- the actual Foundry client, tenant config, credential, and MCP tool list are runtime-derived by `build_platform_agent()`

The defaults also explain why the generic class would otherwise expose a simple fallback name like `platform` rather than building an agent just to read display metadata.[`apps/backend/app/agents/per_request.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/per_request.py#L25-L39) [`apps/backend/app/agents/platform.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/agents/platform.py#L31-L44)

## Focused test

`eval/per_request_override_test.py` is the narrowest proof for this design. It checks that name and description overrides apply, that the proxy still satisfies `SupportsAgentRun`, and that `platform_agent_proxy` keeps its intended identity.[`apps/backend/eval/per_request_override_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/per_request_override_test.py#L1-L39)

## Minimal validation

- `cd apps/backend && uv run python -m eval.per_request_override_test`

Use this check whenever platform serving code or proxy metadata changes.