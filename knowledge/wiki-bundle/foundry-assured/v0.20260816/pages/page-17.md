# Frontend API and proxy layer

The frontend’s server-side API routes do real architectural work: they hide backend URLs from the browser, forward bearer tokens, and bridge CopilotKit to backend AG-UI and hosted-agent endpoints.

## Operational proxy routes

The simple operational proxies are `app/api/evals/route.ts`, `tickets/route.ts`, and `me/route.ts`. Each uses `BACKEND_URL`, forwards the caller’s `Authorization` header when present, disables caching, and converts backend failures into frontend-visible error payloads. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/api/evals/route.ts#L1-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/api/tickets/route.ts#L1-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/api/me/route.ts#L1-L19)

These routes matter because the backend APIs they call are auth-gated. Without token forwarding the UI would appear logged in while all server-side reads fail.

## Auth fetch wrapper

Admin and tenant UIs do not manually attach tokens everywhere. `lib/auth/api.ts` centralizes that by using the MSAL singleton to acquire a silent token and set the `Authorization` header when possible. If silent acquisition fails, the request is still sent and the caller surfaces the resulting 401 instead of forcing a redirect. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/lib/auth/api.ts#L1-L7) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/lib/auth/api.ts#L11-L26)

## Admin and tenant catch-all proxies

The admin and tenant pages use `/api/admin/*` and `/api/tenant/*` route families as the frontend boundary to backend Graph and tenant management APIs. Even when the UI looks like a direct admin console, the browser never talks to Microsoft Graph or tenant persistence directly; it only talks to these proxy surfaces plus the backend. The UI code demonstrates the dependency by routing all calls through `authedFetch('/api/admin/...')` and `authedFetch('/api/tenant/...')`. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/admin/AdminUsers.tsx#L25-L30) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/admin/Connections.tsx#L45-L49)

## CopilotKit runtime bridge

The most important proxy surface is `/api/copilotkit`. The console and legacy chat components configure `CopilotKitProvider` to talk to that route and pass the bearer token in provider headers. That route is the frontend-side runtime bridge for both live backend AG-UI domains and hosted twins. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/chat/HelpdeskApp.tsx#L28-L35) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/console/AssuranceConsole.tsx#L61-L65)

Because the provider is configured once per console instance, a broken `/api/copilotkit` route breaks all domain chats at once.

## Coupling to backend routes

The proxy layer is tightly coupled to backend route names such as `/eval/foundry`, `/tickets`, `/me`, `/helpdesk-hosted`, `/platform-hosted`, and per-domain mount paths. Backend route changes are therefore frontend API changes too, even if the browser-facing page URL stays stable. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/evaluation/api.py#L39-L45) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/tickets/api.py#L9-L15) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/hosted/api.py#L12-L34)

## Validation

After proxy-layer changes, the fastest checks are:

- browser smoke through `/d/<domain>`
- `/evals` and `/tickets` page loads
- admin/tenant page network calls
- Playwright smoke if auth is available

This layer is small but integration-heavy, so UI-plus-network checks beat isolated unit reasoning.
