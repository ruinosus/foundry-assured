These pages are the non-chat half of the frontend. They expose persistent or operational state: user and connection administration, live evaluation results, and the ticket list created by the helpdesk workflow.[`apps/frontend/app/tickets/page.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/app/tickets/page.tsx#L1-L10) [`apps/frontend/app/evals/page.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/app/evals/page.tsx#L1-L10)

## Tickets page

`TicketsView` is a client component that fetches `/api/tickets`, renders a table, and explains that tickets are only created after chat escalation approval. This page is read-only from the frontend’s perspective.[`apps/frontend/components/tickets/TicketsView.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/components/tickets/TicketsView.tsx#L3-L15) [`apps/frontend/components/tickets/TicketsView.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/components/tickets/TicketsView.tsx#L19-L53)

## Evaluations page

`EvalsView` fetches `/api/evals`, expects live Foundry project data, and links users to the Foundry portal report URLs. It is a dashboard over backend operational data rather than a locally computed report page.[`apps/frontend/components/evals/EvalsView.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/components/evals/EvalsView.tsx#L3-L23) [`apps/frontend/components/evals/EvalsView.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/components/evals/EvalsView.tsx#L46-L66)

## Admin pages

The admin pages are route-level wrappers that dynamically import heavy client components and show a friendly denial state when the current user lacks the `Admin` role.[`apps/frontend/app/admin/users/page.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/app/admin/users/page.tsx#L3-L11) [`apps/frontend/app/admin/users/page.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/app/admin/users/page.tsx#L13-L28) [`apps/frontend/app/admin/connections/page.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/app/admin/connections/page.tsx#L3-L11) [`apps/frontend/app/admin/connections/page.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/app/admin/connections/page.tsx#L13-L28)

The role signal comes from `useMyRoles()`, which reads `/api/me` because the access token’s `roles` claim is authoritative for this app, not the SPA’s id token.[`apps/frontend/lib/auth/roles.ts`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/lib/auth/roles.ts#L3-L23)

## Security boundary

Frontend admin gating is convenience, not authority. The code comments say this explicitly in multiple places: pages hide UI for non-admins, but the real gate is server-side on every admin or tenant endpoint.[`apps/frontend/app/admin/users/page.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/app/admin/users/page.tsx#L3-L4) [`apps/frontend/app/admin/connections/page.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/app/admin/connections/page.tsx#L3-L4) [`apps/frontend/components/shell/AppShell.tsx`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/components/shell/AppShell.tsx#L100-L103)

## Backend dependency map

- tickets page → backend `/tickets`
- evals page → backend `/evals`
- admin users page → backend admin/Graph APIs
- admin connections page → backend shared-mode `/tenant/*` APIs

This is why `admin-evals-and-tickets` is not one cohesive data model; it is one operational workspace surface over several backend families.

## Minimal validation

- `cd apps/frontend && npm run typecheck`
- `cd e2e && npm test`

Typecheck catches prop and import drift; Playwright exercises the real cross-system UI.