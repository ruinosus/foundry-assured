---
type: ui
title: Admin and Operations UI
description: "Frontend pages for user management, tenant connections, evaluations, and tickets, and how they map onto backend admin, tenancy, and operational APIs."
tags: [frontend, admin, operations]
---
# Admin and operations UI

The admin and operations surfaces are the frontend pages that expose backend control-plane and audit information without pushing those responsibilities into the browser.

## Users and roles page

`components/admin/AdminUsers.tsx` is the user and role-assignment UI. Every action goes through backend `/api/admin/*` routes, and the component description makes the boundary explicit: the backend holds app-only Graph credentials, every call is re-gated server-side by the Admin role, and the UI is only a convenience layer. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/admin/AdminUsers.tsx#L3-L5) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/admin/AdminUsers.tsx#L25-L30) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/admin/AdminUsers.tsx#L40-L58)

## Connections page

`components/admin/Connections.tsx` is the tenant onboarding and connection lifecycle UI. It never asks the operator to enter a secret value; it stores Foundry connection ids or Key Vault references only, mirroring the backend’s “never store secrets” stance. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/admin/Connections.tsx#L3-L7) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/admin/Connections.tsx#L125-L132)

The page also exposes onboarding, data-plane config, connection CRUD, and domain entitlement state, so it is the main UI for exercising shared-mode tenant configuration and the live admin flows later covered by `tenant_admin_e2e_test.py`, `domains_api_test.py`, and enabled-domain round-trip tests. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/tenant_admin_e2e_test.py#L12-L23) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/registry/domains_api_test.py#L29-L58) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/enabled_domains_roundtrip_test.py#L37-L53)

## Tickets and evals

The `/tickets` and `/evals` pages depend on frontend proxy routes that call backend operational APIs. Those pages are read-only audit surfaces over durable backend state and offline eval outputs, not client-side computations. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/api/tickets/route.ts#L1-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/api/evals/route.ts#L1-L24)

## Shared auth wrapper

Both admin components rely on `authedFetch` for token propagation, so auth changes at that wrapper affect the entire admin/ops UI surface. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/lib/auth/api.ts#L1-L26)

## Operational guidance

When admin pages break, check in this order:

1. frontend token acquisition (`authedFetch`)
2. frontend proxy route
3. backend auth/role gate
4. backend downstream dependency (Graph or tenant store)

The browser UI is usually the top of the chain, not the source of truth.
