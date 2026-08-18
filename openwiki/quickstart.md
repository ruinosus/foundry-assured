---
type: guide
title: OpenWiki Quickstart
description: "Entry point to the repository wiki, with a task-routing map for backend, frontend, hosted agents, infrastructure, scripts, and validation flows."
tags: [quickstart, navigation]
---

# OpenWiki quickstart

Use this wiki as a source-grounded map of the whole repository.

## Start here by intent

| If you need to change... | Read first |
| --- | --- |
| backend boot, domain mount, or shared-mode wiring | `architecture/overview.md`, `backend/backend-overview.md` |
| helpdesk workflow, memory, or ticket approval | `backend/helpdesk-workflow.md` |
| oncall LangGraph approval/edit flow | `backend/oncall-graph.md` |
| selfwiki or techdocs grounded behavior | `backend/grounded-domains.md`, `backend/knowledge-pipeline.md` |
| platform MCP tools or hosted platform path | `backend/platform-ops.md`, `hosted-agents/hosted-agents.md` |
| tenancy, onboarding, tenant config, or admin APIs | `backend/tenancy-and-admin.md`, `backend/state-and-persistence.md` |
| frontend domain routing, console behavior, or proxies | `frontend/frontend-overview.md`, `frontend/assurance-console.md`, `frontend/frontend-api-proxies.md` |
| admin UI, tickets, evals pages | `frontend/admin-and-operations-ui.md` |
| azd/Bicep deployment or ops scripts | `infrastructure/infra-and-deployment.md`, `infrastructure/scripts-and-runbooks.md` |
| browser-level validation flows | `testing/end-to-end.md` |

## Main sections

- `architecture/` — repository-wide topology and cross-system flows.
- `backend/` — FastAPI composition root, runtime domains, tenancy, knowledge, and tests.
- `frontend/` — Next.js shell, console, proxies, and admin surfaces.
- `hosted-agents/` — hosted packages and backend hosted bridges.
- `infrastructure/` — azd/Bicep deployment and operational scripts.
- `testing/` — browser-level end-to-end coverage.

## Fast validation shortcuts

- backend route or mount change → `cd apps/backend && uv run pytest tests/smoke/routes_snapshot_test.py`
- tenancy or domain entitlement change → `cd apps/backend && uv run pytest tests/tenancy tests/registry`
- grounded retrieval or wiki ingest change → `cd apps/backend && uv run pytest tests/knowledge`
- MCP/tooling change → `cd apps/backend && uv run pytest tests/platform_ops`
- browser UX or auth change → `cd e2e && npm test -- smoke.spec.ts`

## Backlog

- Frontend page-level documentation for the exact catch-all route-handler implementations under `app/api/admin/[...path]`, `app/api/tenant/[...path]`, and `app/api/copilotkit/[[...slug]]` remains evidence-blocked in this run because the filesystem reader refused those bracketed route files directly. The proxy behavior is documented from consuming components and adjacent route handlers, but those exact files should get direct citations in a follow-up pass. Source anchor: `apps/frontend/components/admin/AdminUsers.tsx`, `apps/frontend/components/admin/Connections.tsx`, `apps/frontend/components/console/AssuranceConsole.tsx`.
