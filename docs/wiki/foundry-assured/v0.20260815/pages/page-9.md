# Operations and runtime

This page covers how the backend process starts, what it needs from configuration, and which narrow validation commands map to each subsystem. It is not a deployment runbook; it is the runtime-facing view of the code under `apps/backend`.

## Runtime entrypoint and lifecycle

The process entrypoint is `app.main:app`. `main.py` builds a `FastAPI` instance with a lifespan context manager, preloads the Entra OpenID config on startup when auth is enabled, includes the aggregated HTTP router, mounts live domain endpoints, and closes hosted-agent resources on shutdown ([`apps/backend/app/main.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/main.py#L13-L35), [`apps/backend/app/main.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/main.py#L37-L53)).

The order matters:

1. preload OpenID config so the first authenticated request is not the one paying startup latency,
2. serve all HTTP and domain routes,
3. on shutdown, call `hosted_aclose()` to release async hosted clients and credentials.

If you change startup ordering, preserve those guarantees or document a new lifecycle invariant.

## Configuration surfaces

The backend has two main config layers:

- `PlatformSettings` from `.env` for platform-global behavior like deployment mode, tenant-store backend, Entra app registration ids, global MCP flags, onboarding allow-list, and frontend origin ([`apps/backend/app/core/settings.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/core/settings.py#L11-L47)).
- `TenantConfig` for tenant-scoped data-plane behavior like Foundry endpoints, search endpoints, KB names, ACL groups, memory store, and hosted agent names ([`apps/backend/app/core/tenant.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/core/tenant.py#L18-L105)).

`settings.auth_enabled` is the main runtime switch for identity behavior. If it is false, auth dependencies become no-ops and downstream callers fall back to default credentials or dev identities, keeping the backend bootable locally ([`apps/backend/app/core/settings.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/core/settings.py#L49-L56), [`apps/backend/app/core/auth.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/core/auth.py#L130-L139)).

## Deployment mode implications

`deployment_mode` affects runtime composition immediately at import time:

- `self_hosted` and `dedicated` keep `SingleTenantConfigProvider` and single-tenant auth behavior.
- `shared` swaps to `MultiTenantConfigProvider`, constructs a tenant store, and makes domain entitlement a request-time requirement ([`apps/backend/app/core/auth.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/core/auth.py#L106-L114), [`apps/backend/app/core/tenant.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/core/tenant.py#L171-L266)).

Operationally, this means shared-mode misconfiguration tends to fail on import or startup rather than lazily at first request, which is intentional.

## CORS and frontend coupling

CORS is applied through `CORSMiddleware` in `main.py`, using only `settings.frontend_origin`. The module comment explains why: the AG-UI adapter accepts an `allow_origins` argument but marks it “not yet implemented”, so the backend must own CORS at the FastAPI layer ([`apps/backend/app/main.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/main.py#L1-L10), [`apps/backend/app/main.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/main.py#L35-L42)).

## Hosted resource lifecycle and caching

Hosted clients are process-global caches keyed by hosted agent name. The cache is warmed lazily and cleared only by `aclose()` on shutdown, so long-lived backend instances will reuse these clients. The code includes an explicit multitenant TODO warning that cache scoping is currently per agent name, not per tenant ([`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/services/hosted.py#L18-L45), [`apps/backend/app/services/hosted.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/services/hosted.py#L47-L56)).

That means two operational rules follow from code today:

- do not assume hosted client reuse is tenant-safe in shared mode without further cache scoping,
- preserve `hosted_aclose()` wiring if you modify hosted bridges or app lifespan.

## Local run paths

The top-level README gives the normal backend local run command:

```bash
cd apps/backend && uv run uvicorn app.main:app --port 8000 --reload
```

That command is consistent with the package manifest, which depends on `uvicorn[standard]` and exposes the `app` package as the wheel target (`README.md`, [`apps/backend/pyproject.toml`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/pyproject.toml#L14-L18), [`apps/backend/pyproject.toml`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/pyproject.toml#L48-L53)).

When running locally without auth, expect:

- `require_user` to be a no-op,
- `/me` to return a dev identity with all roles,
- credential seams to use `DefaultAzureCredential`,
- some shared-mode or infra-gated evals to skip or behave differently by design.

## Observability and cost instrumentation in knowledge tooling

The knowledge generator has its own runtime instrumentation path. `wiki_builder.py` can enable Azure Monitor OpenTelemetry export for GenAI spans when `APPLICATIONINSIGHTS_CONNECTION_STRING` is present or retrievable from the Foundry project, and it also tracks run-scoped token and cost totals through `_CostMeter`. This is localized to the generator, not the whole backend web process, but it is part of backend-owned runtime behavior ([`apps/backend/app/knowledge/wiki_builder.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/knowledge/wiki_builder.py#L193-L281)).

## Validation routing by subsystem

| Change area | Focused command | What it proves |
| --- | --- | --- |
| Domain registry or mounts | `uv run python -m eval.domain_registry_test` | Four-domain registry shape and dispatch still hold |
| Prompt definitions | `uv run python -m eval.prompt_contract_test` | Prompt loader and semantic contracts still hold |
| Shared-mode auth or tenant seam | `uv run python -m eval.tenant_resolution_test` | Tenant resolution and provider behavior |
| Memory key behavior | `uv run python -m eval.memory_scope_test` | Tenant-prefixing and single-tenant compatibility |
| Retrieval or ACL changes | `uv run python -m eval.retrieval_acl_parity_test` | Authorized user sees sensitive doc, unauthorized does not |
| Bundle or ingestion changes | `uv run python -m eval.docbundle_contract_test` | Producer-consumer contract still matches |
| Generated wiki changes | `uv run python -m eval.wiki_fidelity_test --component <component>` | Citations resolve to real source files |
| Hosted bridge changes | `uv run python -m eval.platform_hosted_bridge_test` | Hosted platform failure path still emits AG-UI envelope |
| MCP registry or tool filtering | `uv run python -m eval.mcp_registry_test` | Tool governance and visibility semantics |

The backend has many more evals under `apps/backend/eval`, but these are the narrowest first-line checks before more expensive or infra-backed runs.

## Infra-gated tests versus offline-safe tests

The eval suite deliberately separates infra-gated and offline-safe checks. For example:

- `tenant_e2e_test.py` skips cleanly unless shared-mode tenant credentials are configured, because it uses real ROPC token acquisition to prove multi-tenant isolation ([`apps/backend/eval/tenant_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tenant_e2e_test.py#L1-L19), [`apps/backend/eval/tenant_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tenant_e2e_test.py#L135-L170)).
- `mcp_brokering_e2e_test.py` skips unless a live Foundry project endpoint and connection id are present, because it proves real credential brokering rather than mocking it ([`apps/backend/eval/mcp_brokering_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/mcp_brokering_e2e_test.py#L1-L21), [`apps/backend/eval/mcp_brokering_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/mcp_brokering_e2e_test.py#L64-L101)).

Operationally, do not treat a skipped infra-gated test as evidence of success; it is evidence only that the environment was not configured for that proof.

## Safe operational changes

- Keep import-time behavior explicit. Shared-mode store construction and provider switching happen at import on purpose.
- Preserve startup preloading and shutdown cleanup ordering.
- When adding config, decide whether it is truly platform-global or belongs in `TenantConfig`; mixing those layers is how shared-mode bugs become hard to trace.
- For anything affecting hosted clients, tenant resolution, or MCP brokering, plan both a focused offline check and an infra-backed proof.
