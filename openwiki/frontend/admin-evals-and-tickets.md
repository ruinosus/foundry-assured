---
type: frontend-workspace-pages
title: Frontend admin, evals, and tickets pages
description: Workspace pages outside the generic chat console, including admin user management, tenant connections, evaluations, tickets, and their backend proxies.
tags: [frontend, admin, evals, tickets]
---

# Frontend admin, evals, and tickets pages

The frontend has several workspace pages that are not chat consoles but still rely heavily on backend contracts.

## Admin users page

Main component:

- [`apps/frontend/components/admin/AdminUsers.tsx`](../../apps/frontend/components/admin/AdminUsers.tsx)

### Responsibilities

- load users, role assignments, and role vocabulary from `/api/admin/*`
- invite external users,
- create internal users,
- assign roles,
- revoke roles,
- remove users.

### Behavior

The component uses a shared `call(path, init?)` helper based on `authedFetch`. It loads data in parallel and refreshes after any mutation.

The page is a convenience layer only. Server-side enforcement remains in backend `require_role("Admin")` and Graph service calls.

## Connections and tenant page

Main component:

- [`apps/frontend/components/admin/Connections.tsx`](../../apps/frontend/components/admin/Connections.tsx)

### Responsibilities

- show onboarding status from `/api/tenant`
- onboard the tenant if permitted,
- edit data-plane pointers,
- list existing connection records,
- add, edit, and delete connections,
- manage enabled state and role thresholds on connection records.

### Important UI contracts

The page teaches the user that:

- secrets are not entered directly,
- connections point to Foundry or Key Vault references,
- onboarding availability depends on allow-list status,
- tenant state is scoped to the caller's current tenant.

This mirrors backend `tenant.py` semantics closely.

## Evals page

Main component:

- [`apps/frontend/components/evals/EvalsView.tsx`](../../apps/frontend/components/evals/EvalsView.tsx)

### Responsibilities

- fetch `/api/evals` with `cache: "no-store"`
- show live Foundry evaluation runs
- show per-criterion pass counts
- link each run to its Foundry portal report
- handle empty-state guidance by telling the operator to run `uv run python -m eval.run_eval --cloud`

The page treats Foundry as the canonical evaluation store and uses the backend only as a same-origin reader.

## Tickets page

The tickets page consumes `/api/tickets`, which proxies backend `GET /tickets`. Its value is operational visibility: users can see what live workflow escalations actually persisted.

## API proxy inventory

Frontend API routes mediate all workspace page backend calls.

| Frontend route | Backend target family | Used by |
| --- | --- | --- |
| `/api/admin/[...path]` | `/admin/*` | `AdminUsers` |
| `/api/tenant/[...path]` | `/tenant/*` | `Connections` |
| `/api/evals` | `/eval/foundry` | `EvalsView` |
| `/api/tickets` | `/tickets` | tickets page |
| `/api/me` | `/me` | auth and role-aware shell helpers |
| `/api/health` | `/health` | `AppShell` backend status |

These proxy routes keep all browser traffic same-origin and centralize backend URL knowledge.

`authedFetch()` itself has one important degradation rule: it tries `msalInstance.acquireTokenSilent(...)`, but if that fails it sends the request without an `Authorization` header and lets the caller surface the resulting 401 or backend error instead of forcing a redirect from deep inside the fetch helper.

## Relationship to shell navigation

`AppShell.tsx` derives workspace navigation partly from a static list and partly from caller roles:

- everyone sees `Overview`, `Tickets`, and `Evaluations`
- only admins see `Admin` and `Connections`

This is a UX optimization only. Backend APIs still re-check authorization.

## Focused validation

From `apps/frontend/`:

```bash
npm run lint
npm run typecheck
```

For integrated validation, use the browser or Playwright against a running stack and verify:

- admin pages are visible only to admins,
- `/evals` shows Foundry run rows or a graceful empty state,
- `/tickets` reflects newly created live helpdesk tickets,
- connection edits persist and reload correctly in shared mode.

## Related pages

- [Frontend application overview](application-overview.md)
- [Admin and tenant APIs](../backend/admin-and-tenant-apis.md)
- [Evaluations and tickets](../backend/evaluations-and-tickets.md)
