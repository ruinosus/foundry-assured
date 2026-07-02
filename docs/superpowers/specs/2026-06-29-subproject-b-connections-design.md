---
title: 'Design: Sub-project B — connections store + UI'
description: Per-tenant management plane — a tenant Admin self-onboards (Admin role + allow-list) and manages their data-plane pointers + Connection records (references to Foundry connections / Key Vault, never secrets). Built on sub-project A's TenantStore; no OAuth (deferred to C).
type: design
audience: contributor
status: draft
updated: 2026-06-29
---

# Sub-project B — connections store + UI

> Second sub-project of the [SaaS target architecture](./2026-06-29-saas-target-architecture-design.md).
> Builds on **sub-project A** (the `TenantStore`/`TenantRecord`, multi-tenant auth, tenant-scoping),
> now merged to `develop`. Decisions: [ADR-004](../../adr/ADR-004-byo-data-plane-foundry-project.md),
> [ADR-005](../../adr/ADR-005-never-store-secrets.md), [ADR-006](../../adr/ADR-006-tenant-scoped-config.md),
> and the new **[ADR-008](../../adr/ADR-008-foundry-connections-app-configuration.md)**.

## Goal

The **per-tenant management plane**: a tenant **Admin self-onboards** (gated by the Admin app role +
a platform allow-list) and manages, through the web app, their **data-plane pointers** (Foundry
endpoint/model, KB) and their **`Connection` records** — *references* to Foundry connections /
Key Vault, **never secrets**. This is the "connect your own world in the web app" piece. **No OAuth
flow** here (Foundry connections / sub-project C broker credentials).

## Scope boundary (B vs C)

- **B** owns: the `Connection` data model, self-service onboarding + the allow-list gate, the
  `/tenant` API (config + connections CRUD), and the Connections UI. B stores **references +
  governance metadata**, runs **no OAuth**.
- **C** owns: runtime **credential brokering** — reading B's `Connection` records, resolving each
  via `foundry_connection_id` (Foundry identity broker / hosted `get_mcp_tool(project_connection_id)`)
  or `keyvault_ref`, and rewiring the MCP tool-builder (`tools.py`) to read connections instead of
  the flat `mcp_*` fields. (Confirmed: the builder rewiring is C, not B.)

## Non-goals

- Any OAuth flow / consent callback / token exchange (Foundry connections + C).
- Rewiring the MCP tool-builder to consume connections (C).
- Azure App Configuration as the config backend — B ships Table Storage (A's impl); App
  Configuration is the documented production swap ([ADR-008](../../adr/ADR-008-foundry-connections-app-configuration.md)), not built here.
- Platform-admin / cross-tenant back-office (B is each tenant managing its own).

## 1. Data model — `Connection`, extending `TenantRecord`

Per [ADR-008](../../adr/ADR-008-foundry-connections-app-configuration.md), a `Connection` is a
**reference to a Foundry connection / Key Vault**, not a credential store:

```python
@dataclass(frozen=True)
class Connection:
    id: str                            # generated (slug/uuid)
    kind: str                          # a registry server id VERBATIM: github | azdo | azure | entra | learn | m365
                                       #   (the registry catalog is the source of truth — no mcp_/ado aliasing)
    label: str
    foundry_connection_id: str = ""    # the Foundry project connection that brokers auth (Microsoft-native)
    keyvault_ref: str = ""             # alternative: the customer's Key Vault URI (non-Foundry)
    min_role_read: str = "Reader"
    min_role_write: str = "Author"
    enabled: bool = True
    # NO raw secret, NO custom auth_method — Foundry connections / Key Vault authenticate.

@dataclass(frozen=True)
class TenantRecord:                    # extends A's
    tid: str; name: str; tier: str; status: str
    data_plane: TenantConfig
    connections: tuple[Connection, ...] = ()   # NEW
```

**Persistence:** `connections` serialized as JSON in the **same Table entity** as `data_plane`
(`PartitionKey=tid, RowKey="config"`) — atomic read/write with the config, no new `TenantStore`
method (just `put(record)`), within Table limits for a handful of connections. *(Migrate to
separate entities `RowKey=conn:{id}` only if a tenant needs many; the interface allows it.)*

**Relationship to the MCP registry (#75):** `registry.py` (servers-as-data) is the **catalog**
(server types + tool governance); a `Connection` is the **per-tenant instance** (which server this
tenant enabled + the reference). `Connection.kind` is a **registry server id verbatim** (`github`,
`azdo`, `azure`, … — note the registry uses `azdo`, not `ado`; no `mcp_` prefix); the catalog is the
single source of truth, so validation is "`kind` ∈ registry ids" and the UI's `kind` dropdown is the
registry list.

## 2. Self-service onboarding + the Admin + allow-list gate

Chicken-and-egg: A's `resolve_tenant` denies (403) when there's no record, but onboarding runs
*before* a record exists — so onboarding has its own path.

```python
# PlatformSettings (global, WE control it)
onboarding_allowed_tids: str = ""      # CSV of tids permitted to onboard (controlled rollout)

# Separate from require_user (which resolves the tenant and would 403 with no record). It
# authenticates via the scheme, sets _current_user (so the handler reads the tid), checks the
# gates, but does NOT resolve the tenant:
def onboarding_guard(user: User = Security(azure_scheme)) -> User:
    _current_user.set(user)                          # so POST /onboard reads the caller's tid
    if "Admin" not in (user.roles or []):            # app role granted by the CUSTOMER's Entra admin post-consent
        raise HTTPException(403, "requires Admin")
    if getattr(user, "tid", None) not in _allowed_tids():  # platform allow-list — WE approve who enters
        raise HTTPException(403, "tenant not allow-listed")
    return user
```

> `getattr(user, "tid", None)` (defensive, like A's `resolve_tenant`): a token without the `tid`
> claim → 403, not a 500. The `/tenant` router is mounted **only in `shared` mode** (§3), where
> `auth_enabled` is necessarily true — so `require_role`'s auth-off no-op branch never applies here.

**Flow:** customer admin-consents the multi-tenant app → their Entra admin assigns **Admin** →
that Admin opens the app → `GET /tenant` shows "Onboard" if no record + `tid` allow-listed →
`POST /tenant/onboard` (uses `onboarding_guard`, **not** tenant resolution) creates the record
(status=active, idempotent). Thereafter A's normal `resolve_tenant` (store presence) governs.

**Two distinct gates** (defense in depth): the **Admin role** (granted by the *customer* via
Entra) **and** the **allow-list** (controlled by *us*). The allow-list gives concrete form to the
"allowed-tenant" A left as a stub.

## 3. API — `app/api/tenant.py` (mirrors `app/api/admin.py`)

`APIRouter(prefix="/tenant")`, same guard pattern as `admin.py`:

| Endpoint | Guard | Behavior |
|---|---|---|
| `GET /tenant` | **`require_role("Admin")` alone** — NOT `require_user` | the current tenant's record, or `{onboarded:false, can_onboard: tid∈allowlist}` |
| `POST /tenant/onboard` | `onboarding_guard` (Admin + allow-list, no resolution) | create the record (idempotent) |
| `PUT /tenant/config` | `require_user` + `require_role("Admin")` | update `data_plane` (Foundry endpoint/model, KB) |
| `GET /tenant/connections` | `require_user` + Admin | list the tenant's connections |
| `POST /tenant/connections` | `require_user` + Admin | add (kind, label, `foundry_connection_id`/`keyvault_ref`, min-roles) |
| `PUT /tenant/connections/{id}` · `DELETE …/{id}` | `require_user` + Admin | edit / remove |

> **Why `GET /tenant` must NOT use `require_user`:** in `shared` mode A's `require_user` calls
> `resolve_tenant`, which **403s when there's no record** — exactly the pre-onboarding state
> `GET /tenant` must report. `require_role("Admin")` validates the token + checks the `roles` claim
> but does **not** resolve the tenant, so it tolerates no record. It computes `can_onboard = tid ∈
> allow-list` in the body **without** 403-ing (so the UI can show the onboard banner). The
> config/connection rows DO use `require_user` because they require an onboarded tenant.

**Tenant-scoping (non-negotiable):** config/connection endpoints operate **only** on the resolved
tenant (`current_tenant_id()` from `require_user`) — `store.get(tid)` → modify → `store.put(record)`.
No `tid` is taken from the path; it comes from the token. Connections are embedded in the record
(§1), so writes are a read-modify-write of the whole record (last-write-wins; an `etag` is a
follow-on if needed). **Mounted only in `shared` mode** — self-hosted reads config from `.env` (A).

## 4. UI — the Connections page (`app/admin/connections/page.tsx`, mirrors `admin/users`)

Admin-gated page (same `useMyRoles`/`isAdmin` + Admin-only nav item as the existing admin pages),
three zones:

1. **Onboarding banner** — only when no record + `tid` allow-listed → "Onboard this tenant" (`POST /tenant/onboard`).
2. **Data-plane form** — Foundry endpoint / model / KB → `PUT /tenant/config`.
3. **Connections table** — kind badge · label · the reference (`foundry_connection_id`/`keyvault_ref`) · min-roles · enabled · edit/delete (`/tenant/connections`).

**Add-connection form:** `kind` (dropdown from the registry catalog) · `label` ·
`foundry_connection_id` **or** `keyvault_ref` · min-roles. **No secret field anywhere** — the UI
physically cannot take a raw secret (the visible enforcement of [ADR-005](../../adr/ADR-005-never-store-secrets.md)/[008](../../adr/ADR-008-foundry-connections-app-configuration.md)).

## 5. Error handling, testing, the B→C handoff

**Error handling (fail-closed + tenant-scoped):**
- Config/connection endpoints: `require_role("Admin")` + resolved tenant → operate only on that
  tenant's record; non-Admin → 403; another tenant is unreachable (no `tid` in the path).
- Onboarding: Admin + allow-list; `tid` not allow-listed → 403; idempotent.
- **Connection validation:** `kind` must be in the registry catalog; must have
  `foundry_connection_id` **or** `keyvault_ref`; the schema has **no secret field**. Store
  unreachable → 503.

**Testing (repo convention: runnable `def main()->int` modules in `apps/backend/eval/`, NO pytest):**
- **Unit, infra-free:** `Connection`/`TenantRecord` round-trip with an embedded connection (extend
  `tenant_store_test`); `onboarding_guard` (Admin + allow-list → ok; missing either → 403, mocked
  user/allow-list); connection validation (bad kind / no ref → reject); tenant-scoping (an endpoint
  only touches `current_tenant_id()`'s record).
- **Frontend:** `tsc` clean; the page mirrors `admin/users` (manual smoke).
- **E2E (infra-gated):** onboard → set config → CRUD a connection against a live store; **skips
  clean offline**.

**B→C handoff:** B produces the **data** (the `Connection` references + `min_role_*`). **C** reads
each enabled connection and resolves the credential via `foundry_connection_id` (Foundry identity
broker / hosted `get_mcp_tool(project_connection_id)`) or `keyvault_ref` (the customer's Key Vault),
and rewires `tools.py` to read connections instead of the flat `mcp_*` fields. B writes no
credential and runs no OAuth.

## Units (for the writing-plans handoff)

- `app/core/tenant_store.py` — add `Connection`; extend `TenantRecord` with `connections` + the JSON (de)serialization.
- `app/core/settings.py` — add `onboarding_allowed_tids` to `PlatformSettings` + an `_allowed_tids()` helper.
- `app/core/auth.py` (or a small `app/core/onboarding.py`) — `onboarding_guard`.
- `app/api/tenant.py` *(new)* — the `/tenant` router (mounted in `shared` mode).
- `app/main.py` — mount the router when `deployment_mode == "shared"`.
- `apps/frontend/app/admin/connections/page.tsx` *(new)* + the admin nav entry + the `/tenant` fetch client.
- `apps/backend/eval/` — `connection_store_test`, `onboarding_guard_test` (+ the infra-gated `tenant_admin_e2e_test`).

## Open questions (for the plan)

1. **`Connection.id` generation** — slug from label vs uuid; uniqueness within the tenant.
2. **Concurrent edits** — last-write-wins for v1; add an `etag`/If-Match if admins collide.
3. **Validating `foundry_connection_id`** — **Decision: accept the string; C validates at runtime**
   (keeps B infra-light, no Foundry SDK call in the management plane). To avoid a silent runtime
   break with no Admin signal, B SHOULD surface a non-blocking "unverified" hint in the UI (the
   reference is saved but not yet confirmed) and rely on C's fail-closed behavior + a clear runtime
   error surfaced back to the Connections page. (Live verification via the Foundry SDK is a
   follow-on if the unverified-hint proves insufficient.)
