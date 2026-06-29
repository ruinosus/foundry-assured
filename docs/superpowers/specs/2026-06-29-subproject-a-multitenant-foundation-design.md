---
title: 'Design: Sub-project A — multi-tenant foundation'
description: The TenantConfigProvider + DEPLOYMENT_MODE seam, multi-tenant Entra (tid/iss + onboarded deny-path), a swappable TenantStore (Table Storage first), and tenant-scoped config/memory — shipped SingleTenant-first with zero behavior change, then MultiTenant.
type: design
audience: contributor
status: draft
updated: 2026-06-29
---

# Sub-project A — multi-tenant foundation

> The "spine" of the [SaaS target architecture](./2026-06-29-saas-target-architecture-design.md).
> Decisions recorded in [ADR-003](../../adr/ADR-003-multitenant-identity-obo.md),
> [ADR-006](../../adr/ADR-006-tenant-scoped-config.md),
> [ADR-007](../../adr/ADR-007-coexistence-deployment-mode.md).

## Goal

Introduce the **one seam** that lets the same codebase run single-tenant (self-hosted, today)
or multi-tenant (shared SaaS): a **`TenantConfigProvider`** selected by **`DEPLOYMENT_MODE`**.
Convert the Entra app to **multi-tenant** with `tid`/`iss` validation and an onboarded deny-path,
behind a swappable **`TenantStore`**. Make per-tenant config and `memory_scope` tenant-scoped —
**SingleTenant-first with zero behavior change** (existing evals stay green), then MultiTenant.

## Scope boundary (A vs B)

A owns the **multi-tenant foundation + the per-tenant config store** (`Tenant` + `DataPlaneConfig`
keyed by `tid`). Sub-project **B** builds **Connections** (the `Connection` entity, OAuth connect
flows, the Connections page) *on top of* A's store, plus onboarding UX. (This refines the target
spec, where the base store was initially grouped under B; A absorbs it because A now ships the
real MultiTenant path.)

## Non-goals

- Connections / external-service OAuth and the Connections UI (sub-project B).
- Credential brokering / passthrough internals (sub-project C).
- Stamp packaging — Managed Application, Lighthouse (sub-project D).
- The control-plane store's production tech choice beyond "cheapest that works, behind an
  interface" — A ships Table Storage; swapping to Cosmos/Postgres is a later impl of `TenantStore`.

## 1. The seam — `PlatformSettings` × `TenantConfig` + the provider

Today there is one global `settings`. Split the two concerns that are conflated in it:

```python
class PlatformSettings(BaseSettings):       # GLOBAL control-plane config — from .env (as today)
    deployment_mode: str = "self_hosted"        # self_hosted | dedicated | shared
    frontend_origin: str
    entra_tenant_id: str                        # the CONTROL PLANE's own tenant (not customers')
    entra_api_client_id: str
    entra_api_client_secret: str
    tenant_store_table: str = "tenants"         # used only in shared mode
    # ... CORS, other platform-level knobs

@dataclass(frozen=True)
class TenantConfig:                          # PER-TENANT — resolved by the provider
    foundry_project_endpoint: str
    foundry_model: str
    azure_search_endpoint: str
    azure_search_knowledge_base: str
    # (Connections are added in sub-project B)
```

**Field classification (where each current `settings` field lands — the rule, applied to all ~20):**

- **`PlatformSettings` (global, control-plane):** `deployment_mode` (new), `tenant_store_table`
  (new), `frontend_origin`, `entra_tenant_id`, `entra_api_client_id`, `entra_api_client_secret`,
  `entra_spa_client_id`, and the derived properties `auth_enabled` + `entra_api_scope`.
- **`TenantConfig` (per-tenant data-plane pointers — everything that names a customer resource):**
  `foundry_project_endpoint`, `foundry_model`, `azure_ai_openai_endpoint`,
  `foundry_embedding_model`, `azure_search_endpoint`, `azure_search_knowledge_base`,
  `azure_storage_account` / `_resource_id` / `_container`, `foundry_memory_store`,
  `hosted_agent_name`, the per-domain KB/index/container fields (`cockpit_search_*`,
  `cockpit_storage_container`, `selfwiki_search_*`, `selfwiki_storage_container`,
  `cockpit_docbundles_path`), and the ACL/group config (`cockpit_acl_*` + the `acl_group_map`
  property). The 4 named in `TenantConfig` above are illustrative; the **rule** is "names a
  customer resource → per-tenant." The plan enumerates the full set when it splits the file.

The provider is the only point of variation:

```python
class TenantConfigProvider(Protocol):
    def current(self) -> TenantConfig: ...                # the current request's tenant config

class SingleTenantConfigProvider:                         # self_hosted / dedicated
    # returns ONE TenantConfig built from .env — identical to today's behavior

class MultiTenantConfigProvider:                          # shared
    # reads the per-request resolved tenant (set in require_user); no extra store hit
```

`DEPLOYMENT_MODE` (env) selects the impl at boot. Call sites switch the **per-tenant** reads from
`settings.foundry_model` to `tenant_config().foundry_model`; platform-global reads stay on
`PlatformSettings`. (`tenant_config()` is a thin module-level accessor over the active provider.)

**Boundaries / dependencies:** the core (agents, workflow, secure_search) depends only on
`tenant_config()` and never knows the mode. `tid` already exists on the `User` object
(`fastapi_azure_auth`), so MultiTenant resolves without re-implementing identity. The resolved
`TenantConfig` is **cached per request** so repeated reads don't re-hit the store.

## 2. `TenantStore` (swappable) + Table Storage + allowed-tenant = store presence

```python
class TenantStore(Protocol):
    def get(self, tid: str) -> TenantRecord | None: ...   # None = not onboarded → deny
    def put(self, rec: TenantRecord) -> None: ...         # onboarding (B) / admin
    def list(self) -> list[TenantRecord]: ...             # admin

@dataclass(frozen=True)
class TenantRecord:                          # what A stores; B extends it with Connections
    tid: str
    name: str
    tier: str                                # shared | dedicated | self_hosted
    status: str                              # active | suspended
    data_plane: TenantConfig                 # customer resource pointers — ZERO secrets
```

**First impl — `TableStorageTenantStore`** (cheapest that serves the purpose):

- **Azure Table Storage** on the **Storage account the project already provisions** — cents, no new resource.
- `PartitionKey = tid`, `RowKey = "config"`; entity properties are the `TenantConfig` pointers.
- **Keyless** (`DefaultAzureCredential` / managed identity), consistent with the rest of the project.
- Swapping to Cosmos/Postgres later = another class implementing `TenantStore`; nothing else changes.

**Allowed-tenant = store presence** (no separate allow-list):

```python
rec = store.get(user.tid)
if rec is None or rec.status != "active":
    raise HTTPException(403, "tenant not onboarded")      # day-1 deny path (ADR-003)
```

A tenant row exists ⟺ the tenant is allowed; onboarding (sub-project B / admin) does the `put`.

**Boundaries:** **SingleTenant uses no store at all** — it returns the `.env`-built `TenantConfig`
directly, so self-hosted/dedicated keep zero database dependency. Table Storage is a
**shared-mode-only** dependency of the managed control plane.

## 3. Identity — multi-tenant scheme + `tid`/`iss` + the request flow

`DEPLOYMENT_MODE` also selects the auth scheme (same `fastapi_azure_auth` library — no hand-rolled
JWT validation):

```python
# auth OFF (local dev) → unchanged in EVERY mode: azure_scheme = None, require_user is a no-op
#   (today's behavior — auth.py gates on settings.auth_enabled). This branch MUST be preserved
#   so step-1 zero-behavior-change holds: with auth off, current_user() is None → memory_scope
#   returns the bare "dev-local" scope, exactly as today.
if not platform.auth_enabled:
    azure_scheme = None
# self_hosted / dedicated  → as today
elif platform.deployment_mode in ("self_hosted", "dedicated"):
    azure_scheme = SingleTenantAzureAuthorizationCodeBearer(tenant_id=platform.entra_tenant_id, ...)
# shared
else:
    azure_scheme = MultiTenantAzureAuthorizationCodeBearer(
        app_client_id=..., validate_iss=True,            # validates sig + aud + iss + exp
        iss_callable=...,                                # expected iss = login.microsoftonline.com/{tid}/v2.0
    )
```

Request flow (shared) — two layers, one choke point:

1. **MultiTenant scheme** validates the token (sig/aud/iss/exp) → `User(tid)`. *(authentication)*
2. **`require_user`** dependency — the single tenant-scoping choke point:
   - set `_current_user` (contextvar, as today);
   - `rec = store.get(user.tid)`; `None`/suspended → **403**;
   - set `_current_tenant` (the resolved `TenantRecord`, **cached for the request**). *(authorization)*
3. Handlers/agents call `tenant_config()` → reads the cached record; `MultiTenantConfigProvider`
   reads `_current_tenant`, not the store again.

**Boundaries / edges:** authentication (the scheme) and authorization/onboarded (store presence)
are separate layers. Guest/personal accounts (`allow_guest_users=True` stays) are an
implementation/test edge: the step-3 validation must cover guest vs member so `tid` resolves the
intended tenant.

## 4. `memory_scope` + the persisted-state guard + the choke point

`memory_scope` has one caller (`workflow/graph.py`), but its output is **persisted state** (Foundry
memory), so a silent prefix change would orphan existing memories:

```python
def memory_scope() -> str:
    user = current_user()
    base = user.oid if (user and user.oid) else "dev-local"
    tid = current_tenant_id()                # the resolved tenant's tid; None outside shared mode
    return f"{tid}:{base}" if tid else base
```

- **SingleTenant:** no `_current_tenant` → `tid is None` → returns `base` **un-prefixed** = today's
  exact behavior; existing memories stay reachable. **Zero behavior change.**
- **MultiTenant:** `f"{tid}:{oid}"` — isolates memory per tenant.

`current_tenant_id()` reads its **own `_current_tenant` contextvar** (set in `require_user`) and
returns `None` when unset — so a unit test sets the contextvar directly, with no store. All
per-tenant state access goes through the provider / the contextvars resolved in `require_user` —
never a global read for tenant data. That is the single, auditable tenant-scoping choke point.

## 5. Migration, testing, error handling

**Migration — the risk isolated behind step 1:**

| Step | What lands | Gate |
|---|---|---|
| **1 — Pure refactor (no multi-tenancy)** | split `PlatformSettings`/`TenantConfig`; `TenantConfigProvider` + `SingleTenantConfigProvider` (built from `.env` = today); route per-tenant reads through `tenant_config()`; `DEPLOYMENT_MODE=self_hosted` default | **existing evals stay green** = identical behavior (the de-risk gate) |
| **2 — Multi-tenancy (off by default)** | `TenantStore` + `TableStorageTenantStore`; `MultiTenantConfigProvider`; MultiTenant scheme + `require_user` resolution + `_current_tenant`; `memory_scope` prefix | gated behind `DEPLOYMENT_MODE=shared` |
| **3 — Prove it** | a second test tenant | `tid` resolves + `iss` validates + unknown `tid` → 403 + config/memory isolated |

**Testing** (repo convention: runnable `def main() -> int` modules under `apps/backend/eval/`,
**not pytest**):

- **Unit, infra-free:** `SingleTenant` returns the `.env` config; deny logic (`store.get=None → 403`);
  `memory_scope` (single = bare, multi = prefixed) — mock the contextvars. Add an in-memory fake
  `TenantStore` for the provider/deny tests.
- **Non-regression gate:** the eval suite **green** after step 1 (proves zero behavior change).
- **Multi-tenant E2E** (needs infra + two tenants): step 3.

**Error handling — all fail-closed:**

- Store unreachable → **503**, never fall back to another tenant.
- `get(tid)=None` / suspended → **403** tenant-not-onboarded.
- Token from a tenant with no store row → rejected (the deny path).
- `DEPLOYMENT_MODE=shared` with no store configured → **fail fast at boot**.

**Units (for the writing-plans handoff):**

- `app/core/settings.py` — split into `PlatformSettings` + `TenantConfig`.
- `app/core/tenant.py` *(new)* — `TenantConfigProvider` (Single/Multi), `tenant_config()`, `current_tenant_id()`.
- `app/core/tenant_store.py` *(new)* — `TenantStore` Protocol + `TableStorageTenantStore` + an in-memory fake for tests.
- `app/core/auth.py` — scheme selection by mode, `require_user` tenant resolution + `_current_tenant`, the `memory_scope` guard.
- The per-tenant `settings.` call sites → `tenant_config()`.

## Open questions (for the plan / later sub-projects)

1. **`iss_callable` exact shape** in the installed `fastapi_azure_auth` version — verify the signature when implementing (rule: don't invent SDK signatures).
2. **Guest/B2B `tid` semantics** — confirm with the second-tenant test which claim identifies the acting tenant for guests.
3. **Table Storage entity size** — if `DataPlaneConfig` grows beyond Table limits, that's the trigger to swap `TenantStore` to Cosmos (the interface already allows it).
