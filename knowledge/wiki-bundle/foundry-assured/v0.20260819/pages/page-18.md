# Frontend overview

The frontend is a Next.js application in `apps/frontend` using CopilotKit, MSAL, and a small set of API routes that proxy backend services. Its package manifest makes the role clear: render the chat/product UI, host demo mode, and forward auth-bearing requests to the backend. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/package.json#L5-L13) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/package.json#L14-L33)

## App shell and providers

`app/layout.tsx` is intentionally tiny: it loads global styles and wraps the app in `Providers`. That means most frontend boot behavior lives in provider composition, not route files. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/layout.tsx#L1-L24)

## Route model

The app has three main surface families:

- **Landing and domain chat**: `/` and `/d/[domain]`
- **Ops/admin pages**: `/evals`, `/tickets`, `/admin/users`, `/admin/connections`
- **Next API proxy routes**: `/api/*` for backend and CopilotKit bridges

The generic domain page is client-only and resolves its behavior from the domain registry, so adding a domain does not require creating a new page component. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/page.tsx#L5-L7) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/page.tsx#L27-L44) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/d/%5Bdomain%5D/page.tsx#L3-L14) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/app/d/%5Bdomain%5D/page.tsx#L16-L24)

## Domain registry

`lib/domains.ts` is the frontend single source of truth for domain identity, labels, kind, prompts, endpoint paths, and optional hosted twin ids. It drives navigation, generic routing, agent ids in `CopilotChat`, and hosted/live toggle availability. Runtime endpoint selection therefore starts in metadata: the domain `id` is the live agent id, and `hostedAgentId` switches the chat runtime to the hosted twin while keeping the same console route. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/lib/domains.ts#L1-L6) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/lib/domains.ts#L8-L25) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/lib/domains.ts#L28-L110)

A practical invariant follows: frontend domain additions are registry changes first, not route additions.

## Demo mode and auth degradation

The dedicated helpdesk and techdocs components show the general pattern the console later generalized: if auth is configured, acquire and refresh MSAL tokens; if not, render chat directly for dev/demo mode. Helpdesk also hides the live/hosted toggle in demo mode because fixtures replay only the live AG-UI path. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/chat/HelpdeskApp.tsx#L21-L35) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/chat/HelpdeskApp.tsx#L47-L70) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/chat/HelpdeskApp.tsx#L104-L159) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/frontend/components/techdocs/TechDocsApp.tsx#L53-L82)

## Main change surfaces

For most frontend work, the canonical files are:

- `lib/domains.ts` for product/domain registration
- `components/console/*` for shared console behavior
- `app/api/*` for proxy boundaries
- `components/admin/*` for admin/tenant operations UI

Those surfaces are expanded in the related frontend pages.
