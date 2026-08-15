---
type: backend-admin-api
title: Admin and tenant management APIs
description: Backend APIs for Graph-backed user administration, tenant onboarding and configuration, connection records, and per-tenant domain entitlement.
tags: [backend, admin, tenant, graph]
---

# Admin and tenant management APIs

The backend has two closely related management surfaces:

- **admin APIs** for user lifecycle and app-role assignment through Microsoft Graph,
- **tenant APIs** for shared-mode onboarding, data-plane configuration, connection references, and domain entitlement.

They live in:

- [`apps/backend/app/api/admin.py`](../../apps/backend/app/api/admin.py)
- [`apps/backend/app/api/tenant.py`](../../apps/backend/app/api/tenant.py)
- with Graph calls implemented in [`apps/backend/app/services/graph.py`](../../apps/backend/app/services/graph.py)

## Admin APIs

### Purpose

The admin APIs give the frontend `/admin/users` page a server-side management plane for Entra users and app-role assignments. The browser never calls Microsoft Graph directly.

### Security model

All routes in `admin.py` use the shared dependency:

- `_admin = Depends(require_role("Admin"))`

Every endpoint therefore requires the caller to hold the backend app's `Admin` role. The role gate is server-side and independent of whether the frontend hides or shows the admin navigation.

### Public routes

| Route | Method | Purpose |
| --- | --- | --- |
| `/admin/roles` | GET | Return the app's role vocabulary for frontend dropdowns. |
| `/admin/users` | GET | List users from Graph. |
| `/admin/users/invite` | POST | Invite an external B2B guest. |
| `/admin/users` | POST | Create an internal member user with a temp password. |
| `/admin/users/{user_id}` | DELETE | Remove a user. |
| `/admin/role-assignments` | GET | List current app-role assignments. |
| `/admin/role-assignments` | POST | Assign an app role to a user or group. |
| `/admin/role-assignments/{assignment_id}` | DELETE | Revoke an assignment. |

### Graph service contract

`services/graph.py` uses app-only credentials, not the caller's delegated token.

Key points:

- `_token()` builds a `ClientSecretCredential` with backend Entra app credentials.
- `_graph(method, path, body)` performs one raw Graph REST call over `urllib`.
- `GraphError(status, message)` wraps HTTP failures in a backend-friendly exception type.
- `_api_sp_id()` and `_app_role_ids()` cache service principal and role-id lookups.

The source comments explicitly state the required app-only Graph permissions:

- `User.ReadWrite.All`
- `User.Invite.All`
- `AppRoleAssignment.ReadWrite.All`
- `Directory.Read.All`

These must be admin-consented on the app registration.

### Why app-only Graph is used

This design means:

- an admin caller is authorized by the app's own role system,
- the backend then acts with the app's Graph identity,
- there is no parallel user store in this repository.

That keeps Entra as the source of truth for identity and role assignment.

## Tenant APIs

The tenant APIs only exist in `shared` deployment mode. `app/api/__init__.py` includes the router conditionally when `settings.deployment_mode == "shared"`.

### Purpose

These routes let an onboarded tenant admin:

- inspect onboarding state,
- onboard the tenant if allow-listed,
- update data-plane config pointers,
- manage connection reference records,
- control which domains are enabled for the tenant.

### Dependency patterns

`tenant.py` intentionally uses two different dependency sets:

- `_admin = Depends(require_role("Admin"))`
- `_user_admin = [Depends(require_user), Depends(require_role("Admin"))]`

This split matters because `GET /tenant` must tolerate a not-yet-onboarded tenant. If it used `require_user`, shared-mode tenant resolution would run first and reject the tenant before onboarding information could be shown.

### Public routes

| Route | Method | Dependencies | Purpose |
| --- | --- | --- | --- |
| `/tenant` | GET | Admin only | Return record if onboarded, otherwise whether caller may onboard. |
| `/tenant/onboard` | POST | `onboarding_guard` | Create the tenant record idempotently. |
| `/tenant/config` | PUT | user plus Admin | Update data-plane pointers in the caller's own record. |
| `/tenant/connections` | GET | user plus Admin | List connection records. |
| `/tenant/connections` | POST | user plus Admin | Add or replace a connection reference. |
| `/tenant/connections/{conn_id}` | DELETE | user plus Admin | Remove a connection reference. |
| `/tenant/domains` | GET | user plus Admin | Return domain catalog and enabled set. |
| `/tenant/domains` | PUT | user plus Admin | Update enabled domain set for this tenant. |

### Onboarding behavior

`onboard(body: OnboardBody | None = None, user: User = Depends(onboarding_guard))` creates the tenant record idempotently. When the tenant is not already present, it seeds `enabled_domains` from `domains_for_tier(body.tier or "shared")` and stores a fresh `TenantConfig()` as the initial data-plane placeholder.

### Tenant scoping rule

All tenant writes are scoped to the caller's resolved tenant. No route accepts a tenant ID path parameter for update operations. Instead:

- `_my_record()` loads the current tenant from `current_tenant_id()`,
- writes perform read-modify-write against that record only.

This prevents an admin from mutating another tenant by guessing an ID in the URL.

If a caller tries to update config, connections, or domain entitlements before the tenant record exists, `_my_record()` raises HTTP 404 `tenant not onboarded`. That is the explicit fail-closed path for scoped writes.

## Connection records

The tenant API uses `Connection` records from `core/tenant_store.py` rather than storing secrets inline.

`ConnectionBody` supports:

- `id`
- `kind`
- `label`
- `foundry_connection_id`
- `keyvault_ref`
- `min_role_read`
- `min_role_write`
- `enabled`

`add_connection()` enforces two important invariants:

1. `validate_kind(body.kind)` must pass or the API returns HTTP 422 `unknown kind: ...`,
2. a connection must provide either `foundry_connection_id` or `keyvault_ref`, otherwise the API returns HTTP 422.

This aligns with the repository's broader rule that secret values live in Foundry or Key Vault, while the control plane stores references.

Deletion also stays tenant-scoped: `delete_connection(conn_id)` rewrites only the current tenant record via `without_connection(_my_record(), conn_id)`. The API does not let callers name a different tenant in the URL.

## Redaction behavior

`_SECRET_CONFIG_FIELDS = ("mcp_github_pat",)` lists per-tenant config fields that should never be echoed back. `_redacted(rec)` returns a copy of the tenant record with those fields blanked.

Even though the newer system prefers connection references, this redaction remains important because the legacy field still exists for self-hosted compatibility.

## Domain entitlement management

The tenant API exposes the same domain catalog defined in `core/tenant.py`.

- `get_domains()` returns `catalog` and the tenant's `enabled` set.
- `put_domains()` rejects unknown IDs with HTTP 422 and preserves canonical catalog order while deduplicating enabled values.

This is the admin control surface for `require_domain(domain_id)` in shared mode.

## Focused tests

Representative test coverage includes:

- `tenant_admin_e2e_test.py`: tenant admin behavior end to end.
- `tenant_e2e_test.py`: tenant lifecycle.
- `connection_store_test.py`, `connection_ops_test.py`, `connection_tools_build_test.py`: connection invariants.
- `domain_gate_test.py`, `domains_api_test.py`, `enabled_domains_roundtrip_test.py`, `tier_domains_test.py`: domain entitlement correctness.
- `onboarding_guard_test.py`: onboarding allow-list and Admin gating.
- `rbac_per_tool_test.py`: downstream consequences of stored connection role thresholds.

## Validation

From `apps/backend/`:

```bash
uv run pytest eval/tenant_admin_e2e_test.py eval/tenant_e2e_test.py eval/connection_store_test.py eval/domain_gate_test.py
```

## Related pages

- [Backend auth and tenancy](auth-and-tenancy.md)
- [Platform domain](platform-domain.md)
- [Infrastructure identity and access](../infrastructure/identity-and-access.md)
- [Frontend admin, evals, and tickets](../frontend/admin-evals-and-tickets.md)
