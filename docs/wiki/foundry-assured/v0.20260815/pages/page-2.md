This page covers the backend APIs that are not part of live domain execution but still matter to operators and the frontend workspace. These routes are aggregated under `api_router` and expose user management, hosted bridge endpoints, eval summaries, ticket persistence, health, and caller identity.[`apps/backend/app/api/__init__.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/__init__.py#L1-L19)

## Health, me, tickets, and evals

These are the simplest operational APIs:

- `/health` is a plain backend liveness surface.[`apps/backend/app/api/health.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/health.py#L1-L4)
- `/me` returns the caller’s role-bearing identity shape used by the frontend to decide whether to show admin UI.[`apps/backend/app/api/me.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/me.py#L1-L22)
- `/tickets` exposes persisted tickets created by the workflow escalation path.[`apps/backend/app/api/tickets.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/tickets.py#L1-L12)
- `/evals` exposes Foundry-hosted eval runs for the frontend evaluations page.[`apps/backend/app/api/evals.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/evals.py#L1-L19)

## Hosted chat bridges

`/helpdesk-hosted` and `/platform-hosted` sit in `app/api/chat.py`. They are operational APIs because they proxy one backend-managed protocol to another, rather than owning core domain logic themselves.[`apps/backend/app/api/chat.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/chat.py#L1-L8) [`apps/backend/app/api/chat.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/chat.py#L12-L34)

The key invariant here is parity of access control with live routes: the hosted endpoints remain behind auth dependencies, and platform-hosted also uses shared-mode domain entitlement checks through `_domain_deps("platform")`.[`apps/backend/app/api/chat.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/chat.py#L12-L18) [`apps/backend/app/api/chat.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/chat.py#L29-L34)

## Admin API and Graph service

Admin user and role management is implemented as backend API plus Graph service. `app/services/graph.py` acquires an app-only Microsoft Graph token using the API app’s own client credentials and then performs Graph REST calls with that app identity.[`apps/backend/app/services/graph.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/graph.py#L1-L15) [`apps/backend/app/services/graph.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/graph.py#L34-L40)

The design intent is explicit: there is no parallel user store. The app drives lifecycle and app-role operations through Graph, with all callers still gated by the backend `Admin` role.[`apps/backend/app/services/graph.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/graph.py#L3-L11)

Capabilities include:

- list users and invite or create users.[`apps/backend/app/services/graph.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/graph.py#L101-L129)
- list app-role assignments and assign or revoke app roles.[`apps/backend/app/services/graph.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/graph.py#L134-L166)
- cache the API service principal id and app role ids to avoid repeated lookups.[`apps/backend/app/services/graph.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/graph.py#L75-L96)

## Ticket persistence

The workflow’s durable side effect is ticket creation, and the operational ticket view depends on that persistence layer. Tickets are created by `create_ticket()` and then served through `/tickets`; the frontend never talks to storage directly.[`apps/backend/app/workflow/escalation.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/workflow/escalation.py#L82-L89) [`apps/backend/app/api/tickets.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/tickets.py#L1-L12)

Infrastructure comments in `resources.bicep` explain why this matters operationally: `/app/data` is mounted on Azure Files so small jsonl records like tickets survive restarts and scale-to-zero.[`infra/resources.bicep`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/infra/resources.bicep#L212-L223)

## Eval readout path

The eval route is a backend operational summary over Foundry project data, not a local static report. The frontend depends on this route to render live project-eval state.[`apps/backend/app/api/evals.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/evals.py#L1-L19) [`apps/backend/app/services/foundry_evals.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/foundry_evals.py#L1-L63)

## Operational boundaries

This API group has two ownership boundaries worth preserving:

1. **tenant self-service is not admin Graph management**. Shared-mode `/tenant/*` APIs mutate a tenant record; admin APIs mutate Entra/Graph-backed user and role state.[`apps/backend/app/api/tenant.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/tenant.py#L1-L7) [`apps/backend/app/services/graph.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/services/graph.py#L1-L15)
2. **frontend visibility is advisory, backend role checks are authoritative**. The backend must keep role enforcement even if the frontend already hides a page.[`apps/backend/app/core/auth.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/core/auth.py#L141-L165)

## Focused tests

Useful backend tests for this surface include:

- `eval/tenant_admin_e2e_test.py` for shared-mode admin and record mutation flows.[`apps/backend/eval/tenant_admin_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/tenant_admin_e2e_test.py#L1-L24)
- `eval/connection_ops_test.py` and `eval/connection_store_test.py` for connection mutation semantics that back `/tenant/connections`.[`apps/backend/eval/connection_ops_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/connection_ops_test.py#L1-L59) [`apps/backend/eval/connection_store_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/connection_store_test.py#L1-L56)
- `eval/platform_hosted_bridge_test.py` for one hosted chat bridge failure mode.[`apps/backend/eval/platform_hosted_bridge_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/platform_hosted_bridge_test.py#L1-L18)

## Minimal validation

- `cd apps/backend && uv run python -m eval.connection_ops_test`
- `cd apps/backend && uv run python -m eval.platform_hosted_bridge_test`

Those are narrow checks for a representative control-plane mutation surface and one operational hosted bridge path.