---
type: reference
title: Frontend API and Proxy Layer
description: "Next.js route handlers that proxy backend services and CopilotKit traffic, including token forwarding, admin and tenant proxies, and the source-document confirmation bridge."
tags: [frontend, api, proxy, auth]
openwiki:
  roles: [integration, operations]
  change_kinds: [http, auth]
  source_paths:
    - apps/frontend/app/api/source/[domain]/[name]/route.ts
    - apps/frontend/app/api/copilotkit/[[...slug]]/route.ts
    - apps/frontend/lib/auth/api.ts
  symbols:
    - GET
    - authedFetch
  test_paths:
    - apps/frontend/scripts/verify-thread-citations.mjs
  invariants:
    - Proxy routes must forward bearer tokens when available.
    - Source-document proxy responses must preserve authorization status distinctions and no-store caching.
  validation_commands:
    - cd apps/frontend && node scripts/verify-thread-citations.mjs
---
# Frontend API and proxy layer

The frontend’s server-side API routes do real architectural work: they hide backend URLs from the browser, forward bearer tokens, and bridge CopilotKit to backend AG-UI and hosted-agent endpoints. The newer source-document confirmation route belongs in the same layer because the browser still never talks to the backend directly for cited documents. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/app/api/source/%5Bdomain%5D/%5Bname%5D/route.ts#L1-L19) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/lib/auth/api.ts#L1-L26)

This page complements Assurance Console, which is the main consumer of the `/api/source/*` route.

## Operational proxy routes

The simple operational proxies remain `app/api/evals/route.ts`, `tickets/route.ts`, and `me/route.ts`. Each uses `BACKEND_URL`, forwards the caller’s `Authorization` header when present, disables caching, and converts backend failures into frontend-visible error payloads. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/app/api/evals/route.ts#L1-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/app/api/tickets/route.ts#L1-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/app/api/me/route.ts#L1-L19)

These routes still matter because the backend APIs they call are auth-gated. Without token forwarding the UI would appear signed in while all server-side reads fail.

## Auth fetch wrapper

Admin, tenant, and source-viewer requests do not attach tokens manually. `lib/auth/api.ts` centralizes that by using the MSAL singleton to acquire a silent token and set the `Authorization` header when possible. If silent acquisition fails, the request is still sent and the caller surfaces the resulting `401` rather than forcing a redirect. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/lib/auth/api.ts#L1-L26)

That wrapper is now part of the evidence path too, because `SourceViewer` uses `authedFetch(...)` for `/api/source/*`. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/components/console/SourceViewer.tsx#L16-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/components/console/SourceViewer.tsx#L81-L99)

## Admin and tenant catch-all proxies

The admin and tenant pages still use `/api/admin/*` and `/api/tenant/*` route families as the frontend boundary to backend Graph and tenant-management APIs. The UI code shows the dependency by routing calls through `authedFetch('/api/admin/...')` and `authedFetch('/api/tenant/...')`. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/components/admin/AdminUsers.tsx#L25-L30) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/components/admin/Connections.tsx#L45-L49)

## CopilotKit runtime bridge

The most important proxy surface is still `/api/copilotkit`. `AssuranceConsole` configures `CopilotKitProvider` to talk to that route and passes both the bearer token and `Accept-Language` in provider headers. That route remains the frontend-side runtime bridge for live backend AG-UI domains and hosted twins. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/components/console/AssuranceConsole.tsx#L83-L94) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/app/api/copilotkit/%5B%5B...slug%5D%5D/route.ts#L1-L33)

Because the provider is configured once per console instance, a broken `/api/copilotkit` route still breaks all domain chats at once.

## Source-document confirmation proxy

`app/api/source/[domain]/[name]/route.ts` is the new evidence-specific proxy. It forwards the caller’s `Authorization` header to the backend `/source/{domain}/{name}` route, keeps `cache: "no-store"`, parses the backend JSON payload, and preserves the backend `Cache-Control` header if present. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/app/api/source/%5Bdomain%5D/%5Bname%5D/route.ts#L11-L19) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/app/api/source/%5Bdomain%5D/%5Bname%5D/route.ts#L22-L48)

Two details are important for future changes:

- the proxy preserves `401`, `403`, `404`, and `400` distinctly instead of collapsing them to `502`, because the UI needs to tell “session expired”, “not authorized”, and “missing source” apart; [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/app/api/source/%5Bdomain%5D/%5Bname%5D/route.ts#L15-L19) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/components/console/SourceViewer.tsx#L84-L95)
- the proxy intentionally replays backend `Cache-Control` because the backend is the canonical source of the no-store rule for ACL-controlled content. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/frontend/app/api/source/%5Bdomain%5D/%5Bname%5D/route.ts#L34-L48) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/api.py#L85-L112)

That makes the proxy a consumer-facing mirror of the backend’s source-confirmation contract, not just a dumb passthrough.

## Coupling to backend routes

The proxy layer stays tightly coupled to backend route names such as `/eval/foundry`, `/tickets`, `/me`, `/helpdesk-hosted`, `/platform-hosted`, `/source/{domain}/{name}`, and per-domain mount paths. Backend route changes are therefore frontend API changes too, even if the browser-facing page URL stays stable. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/evaluation/api.py#L39-L45) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/tickets/api.py#L9-L15) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/hosted/api.py#L12-L34) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/knowledge/api.py#L52-L113)

## When to edit this page

Consult this page when you are:

- changing a Next.js route handler under `app/api/*`,
- adding a new backend-to-frontend proxy boundary,
- changing auth header forwarding or cache policy,
- changing the source-viewer API contract but not the UI semantics themselves.

For UI rendering, evidence placement, and conversation replay, continue in Assurance Console.

## Validation

Start with the narrowest checks that cross the proxy boundary:

- `cd apps/frontend && node scripts/verify-thread-citations.mjs` when source or conversation replay data shapes change,
- manual `/d/selfwiki` or `/d/techdocs` citation click-through when changing `/api/source/*`, because that is the narrowest consumer-facing smoke test for the proxy and backend `/source` route together.

Broader browser smoke or E2E checks are conditional, not default.
