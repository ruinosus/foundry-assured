# Operations and runtime behavior

This page is the canonical home for backend runtime ownership that is not specific to one product domain: environment-driven settings, process lifecycle, client caches, operational routes, and the known TODOs that shape safe changes. The source splits those concerns across `app/main.py`, `app/core/settings.py`, router-level operational APIs, and `app/services/hosted.py`. [main.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/main.py#L1-L53) [settings.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/core/settings.py#L1-L63) [hosted.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/services/hosted.py#L18-L56)

## Global settings ownership

`PlatformSettings` is the backend's process-global configuration model. It is the only place that should own values affecting the whole process rather than one tenant, including:

- deployment mode
- tenant-store account/table/backend
- Entra backend and SPA app-registration settings
- platform-global MCP flags and Learn URL
- onboarding allow-list
- CORS frontend origin [settings.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/core/settings.py#L11-L63)

This separation is intentional. The module docstring says per-tenant data-plane config belongs in `app.core.tenant`, not here, so changes to a setting should start by deciding whether the value is global or tenant-scoped. [settings.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/core/settings.py#L1-L6) [tenant.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/core/tenant.py#L18-L24)

## Startup and shutdown lifecycle

The FastAPI app defines a lifespan context manager with two operational duties:

1. pre-load the Entra OpenID config when `azure_scheme` exists, so the first authenticated request is faster
2. close hosted-agent clients on shutdown via `hosted_aclose()` [main.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/main.py#L26-L33)

The composition root also applies CORS manually because the AG-UI helper's `allow_origins` argument is documented as not yet implemented. That means CORS changes belong in `app.main`, not in domain-mount code. [main.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/main.py#L8-L10) [main.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/main.py#L35-L42)

## Deployment mode branching

Runtime behavior diverges materially by `deployment_mode`:

- `self_hosted` and `dedicated` stay effectively single-tenant, keep the default `SingleTenantConfigProvider`, and do not build a tenant store. [auth.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/core/auth.py#L106-L113)
- `shared` swaps in `MultiTenantConfigProvider`, constructs `_tenant_store` at boot, and adds `require_domain()` to mounted domain dependencies. [auth.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/core/auth.py#L77-L94) [domains.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/domains.py#L102-L109)

The store backend itself is configurable: `memory` is explicitly dev/CI only so shared mode can boot offline, and `table` is the default production path that requires `TENANT_STORE_ACCOUNT_URL`. [settings.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/core/settings.py#L16-L23) [auth.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/core/auth.py#L77-L94)

`eval.shared_boot_smoke_test` exists because this boot path is fragile: it verifies that shared mode plus auth plus in-memory store can import `app.main` cleanly without touching unresolved tenant config. [shared_boot_smoke_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/shared_boot_smoke_test.py#L1-L40)

## Hosted-client cache

`app.services.hosted` keeps a process-global `_clients` cache keyed by hosted-agent name. Each entry contains the async OpenAI client, the `AIProjectClient`, and the credential used to construct it. `aclose()` iterates that cache, closes all three objects per entry, and clears the dictionary. [hosted.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/services/hosted.py#L18-L56)

This cache is intentionally generic enough to serve multiple hosted twins, but the source contains an explicit multitenant caveat: the cache is keyed only by agent name, so the first tenant that warms a hosted agent binds that cached client. The code marks this as a TODO to scope or bust the cache per tenant when the multitenant provider lands fully. Treat that as a real runtime hazard when changing hosted-path behavior. [hosted.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/services/hosted.py#L23-L44)

## Operational endpoints and their backing stores

### `/healthz`

`GET /healthz` is the liveness probe. It returns `{"status": "ok"}` and has no auth dependency. [api/health.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/api/health.py#L1-L8)

### `/tickets`

`GET /tickets` returns tickets created by the workflow approval path. The route is sign-in gated, and its docstring says persistence lives in `data/tickets.jsonl`, which becomes an Azure Files mount in deployed environments so tickets survive scale-to-zero. [api/tickets.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/api/tickets.py#L9-L16)

### `/eval/runs` and `/eval/foundry`

`GET /eval/runs` reads the offline harness mirror at `apps/backend/eval/runs.jsonl`, reverses it to newest-first, and serves the local run history. `GET /eval/foundry` instead reads live evaluation runs from the Foundry project, which the frontend treats as canonical. [api/evals.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/api/evals.py#L12-L33) [api/evals.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/api/evals.py#L36-L42)

## Hosted protocol bridges

The backend has two hosted bridges in `app.services.hosted`:

- `stream_agui(body, agent_name)` converts a hosted agent's Responses stream into AG-UI SSE. [hosted.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/services/hosted.py#L72-L105)
- `stream_platform_agui(body)` is intended to relay the platform hosted agent's Invocations SSE back to the frontend. [hosted.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/services/hosted.py#L121-L182)

Test coverage is split by bridge type. `eval.platform_hosted_bridge_test` exercises the infra-free failure envelope for the platform Invocations bridge, `eval.hosted_platform_smoke_test` validates that the hosted-platform scaffold declares the Invocations protocol, and `eval.platform_hosted_e2e_test` is the infra-gated placeholder for real deployed-endpoint verification. The non-platform hosted path is covered indirectly by `eval.hosted_build_test`, which verifies the hosted connection-build contract that `stream_agui` depends on when assembling hosted MCP tools. [platform_hosted_bridge_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/platform_hosted_bridge_test.py#L1-L56) [hosted_platform_smoke_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/hosted_platform_smoke_test.py#L1-L38) [platform_hosted_e2e_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/platform_hosted_e2e_test.py#L1-L25) [hosted_build_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/hosted_build_test.py#L1-L50)

The platform bridge is the riskiest runtime area today because the source contains multiple explicit TODOs:

- the exact Invocations data-plane scope is not pinned by an SDK constant offline [hosted.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/services/hosted.py#L148-L151)
- the exact request-body shape expected by the deployed endpoint is not verified offline [hosted.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/services/hosted.py#L153-L156)
- the claimed passthrough is not byte-identical yet, because `aiter_lines()` strips separators and likely needs replacement with raw-byte iteration [hosted.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/services/hosted.py#L168-L177)

If you change this code, preserve the current failure-path contract: on exceptions it emits a clean AG-UI run envelope with `RunStarted`, `TextMessageStart`, `TextMessageEnd`, and `RunError` instead of crashing the stream. `eval.platform_hosted_bridge_test` guards that behavior in an infra-free way. [hosted.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/app/services/hosted.py#L178-L182) [platform_hosted_bridge_test.py](https://github.com/ruinosus/foundry-assured/blob/4d10c9a42e5d5c2a2b7f60d26a3e694620a9bcaa/apps/backend/eval/platform_hosted_bridge_test.py#L1-L56)

## Runtime configuration matrix

| Concern | Owner | Example knobs |
|---|---|---|
| Auth enablement and bearer validation | `PlatformSettings` and `app.core.auth` | `entra_tenant_id`, `entra_api_client_id`, `entra_api_client_secret` |
| Shared-mode control plane | `PlatformSettings` and tenant store factory | `deployment_mode`, `tenant_store_backend`, `tenant_store_account_url`, `tenant_store_table` |
| CORS | `app.main` | `frontend_origin` |
| MCP global switch | `PlatformSettings` | `mcp_enabled`, `mcp_learn_url` |
| Per-tenant data plane | `TenantConfig` | Foundry endpoint, KB names, search index names, ACL groups, memory-store name |
| Prompt source directory | `app.agents.prompts` | `AGENTS_DIR` |

This matrix is the shortest route from an operational change request to the correct code owner.

## Focused validation

- Shared boot path: `uv run python -m eval.shared_boot_smoke_test`
- Hosted platform failure envelope: `uv run python -m eval.platform_hosted_bridge_test`
- Foundry eval API route still reading locally and remotely: `uv run python -m eval.hosted_build_test` for hosted-path builder assumptions, plus manual route smoke on `/eval/*`
