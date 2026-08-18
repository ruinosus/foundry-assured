---
type: service
title: Tenancy and Admin
description: "Tenant resolution, control-plane persistence, onboarding and admin APIs, and the invariants that make shared mode safe without moving business domains into the shared kernel."
tags: [backend, tenancy, admin, multitenancy]
---

# Tenancy and admin

Tenancy is the backend subsystem that turns deployment mode into runtime behavior. The module split recorded in `tenant_resolution.py` is important: auth remains shared infrastructure, but tenant resolution and tenant store ownership moved into the `tenancy` domain. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_resolution.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/main.py#L31-L39)

## Tenant installation and resolution

`install()` is called once by the composition root. In shared mode only, it swaps in `MultiTenantConfigProvider`, builds the control-plane tenant store, and registers a post-authenticate hook that resolves the current tenant. Outside shared mode it is a no-op. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_resolution.py#L85-L106)

`resolve_tenant(user, store)` is the authorization choke point: it looks up the user’s `tid`, rejects missing or non-active tenants with HTTP 403, and writes the tenant into current request state. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_resolution.py#L61-L69)

That means tenant resolution is not just routing; it is also the first shared-mode access-control gate.

## Tenant store ownership

Tenant persistence lives in `tenant_store.py`. `TenantRecord` stores tenant id, tier, status, data-plane config, per-tenant MCP `Connection` records, and enabled domains. The store is intentionally swappable between `InMemoryTenantStore` and `TableStorageTenantStore`. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_store.py#L15-L37) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_store.py#L79-L99) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_store.py#L111-L145)

The composition root injects the valid MCP server catalog through `set_server_catalog`, and `validate_kind()` raises if that catalog was never registered. This prevents a subtle but dangerous failure mode where every connection kind would look invalid because of wiring, not data. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_store.py#L40-L65)

## Memory scope and tenant-aware identity

Tenancy also owns `memory_scope()`. It prefixes the user’s oid with tenant id only when a current tenant exists, preserving old single-tenant memory ids while ensuring shared-mode memories cannot collide across tenants. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_resolution.py#L71-L82)

This function is an invariant boundary between shared auth and tenant-aware state. If it moved into the shared kernel, shared code would need tenant imports again.

## Tenant management API

`app/modules/tenancy/api.py` exposes the per-tenant management API in shared mode. The router is Admin-gated and intentionally distinguishes between:

- `GET /tenant`: must tolerate not-yet-onboarded tenants, so it cannot rely on tenant resolution first.
- Config/connection/domain endpoints: require both authenticated user and Admin role on an onboarded tenant.

[Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/api.py#L1-L7) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/api.py#L26-L41) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/api.py#L72-L79) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/api.py#L103-L149)

The API writes only the caller’s own tenant record; no endpoint accepts an arbitrary tenant id path parameter for mutation. Read-modify-write is explicit: `_my_record()` resolves the current tenant from `current_tenant_id()`, config updates replace only `data_plane`, connection writes validate kind plus reference presence before `with_connection`, deletes use `without_connection`, and domain updates reject unknown ids then serialize enabled domains in catalog order. `GET /tenant` also returns a redacted record that blanks secret-bearing config fields before sending them back to the UI. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/api.py#L31-L41) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/api.py#L62-L69) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/api.py#L103-L123) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/api.py#L126-L149)

`current_tenant_id()` and `tenant_config()` are the request-time resolution surfaces every downstream domain uses after the post-auth hook has installed the active tenant context. Unknown or suspended tenants never reach those downstream surfaces because `resolve_tenant()` 403s first. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant_resolution.py#L61-L69) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tenancy/internal/tenant.py#L1-L1)

## Admin API

The separate `admin` module handles user lifecycle and app-role assignment through Microsoft Graph app-only credentials. `api_admin.py` is entirely Admin-gated server-side, and `internal/graph.py` makes Graph calls using the API app’s own identity, not the browser caller’s token. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/admin/api_admin.py#L1-L6) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/admin/api_admin.py#L17-L29) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/admin/internal/graph.py#L1-L15) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/admin/internal/graph.py#L34-L65)

A useful invariant is encoded in `_token()`: missing Entra app credentials are converted into a clean `GraphError(503)` instead of leaking raw credential-library exceptions to the UI. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/admin/internal/graph.py#L34-L58)

## Shared-mode proof tests

Tenancy’s highest-value tests are the shared-mode E2E and store tests. `tenant_e2e_test.py` proves that two real tenants resolve to distinct `TenantRecord` values, unauthorized or suspended tenants 403, and `memory_scope()` prefixes by tenant id so A and B cannot collide. `enabled_domains_roundtrip_test.py` proves enabled-domain serialization, legacy-default handling, and persistence semantics, while `domains_api_test.py` proves onboard seeding plus read/tighten/reject-unknown behavior for the tenant-scoped domain catalog. `tenant_admin_e2e_test.py` then proves the live onboarding/config/connection CRUD path against the real Table Storage-backed tenant store. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/tenant_e2e_test.py#L7-L19) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/tenant_e2e_test.py#L178-L198) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/tenant_e2e_test.py#L236-L260) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/enabled_domains_roundtrip_test.py#L1-L7) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/enabled_domains_roundtrip_test.py#L37-L53) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/registry/domains_api_test.py#L1-L6) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/registry/domains_api_test.py#L29-L58) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/tenant_admin_e2e_test.py#L12-L23)

For code changes, the narrow validation set is usually:

- `tests/tenancy/tenant_resolution_test.py`
- `tests/tenancy/tenant_store_test.py`
- `tests/tenancy/memory_scope_test.py`
- `tests/tenancy/enabled_domains_roundtrip_test.py`
- `tests/registry/domains_api_test.py`
- `tests/tenancy/tenant_admin_e2e_test.py`

Run those before broader route or E2E suites.
