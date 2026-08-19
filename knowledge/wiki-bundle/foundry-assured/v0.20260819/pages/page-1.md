# OpenWiki quickstart

Use this wiki as a source-grounded map of the whole repository.

## Start here by intent

| Change area or user intent | Relevant wiki page | Exact source entry points | Important symbols or types | Focused tests | Minimal validation command |
| --- | --- | --- | --- | --- | --- |
| backend boot, domain mount, or shared-mode wiring | `architecture/overview.md`, `backend/backend-overview.md` | `apps/backend/app/main.py`, `apps/backend/app/registry.py` | `include_routers`, `mount_domains`, `DOMAIN_KINDS`, `DomainSpec` | `apps/backend/tests/smoke/routes_snapshot_test.py`, `apps/backend/tests/registry/domain_registry_test.py` | `cd apps/backend && uv run pytest tests/smoke/routes_snapshot_test.py tests/registry/domain_registry_test.py` |
| grounded selfwiki or techdocs runtime behavior | `backend/grounded-domains.md`, `backend/knowledge-pipeline.md` | `apps/backend/app/modules/grounded/internal/grounded.py`, `apps/backend/app/modules/grounded/internal/framework_agent.py`, `apps/backend/app/modules/knowledge/internal/retrieval.py` | `stream_grounded`, `build_grounded_agent`, `mount_grounded_via_framework`, `retrieve` | `apps/backend/tests/grounded/framework_agent_test.py`, `apps/backend/tests/grounded/sources_message_id_test.py`, `apps/backend/tests/knowledge/retrieval_acl_parity_test.py` | `cd apps/backend && uv run pytest tests/grounded/framework_agent_test.py tests/grounded/sources_message_id_test.py tests/knowledge/retrieval_acl_parity_test.py` |
| source-document confirmation or document ACL recheck | `backend/knowledge-pipeline.md`, `frontend/frontend-api-proxies.md` | `apps/backend/app/modules/knowledge/api.py`, `apps/backend/app/modules/knowledge/internal/document.py`, `apps/frontend/app/api/source/[domain]/[name]/route.ts` | `read_source`, `authorized_document`, `NomeDocumentoInvalido` | `apps/backend/tests/knowledge/document_api_test.py`, `apps/backend/tests/knowledge/document_access_test.py` | `cd apps/backend && uv run pytest tests/knowledge/document_api_test.py tests/knowledge/document_access_test.py` |
| conversation persistence, replay, or usage accounting | `backend/state-and-persistence.md`, `frontend/assurance-console.md` | `apps/backend/app/modules/conversations/internal/store.py`, `apps/backend/app/modules/conversations/internal/listing.py`, `apps/backend/app/modules/conversations/internal/recorder.py`, `apps/frontend/lib/thread-history.ts` | `sanitize`, `record_turn`, `bind_dependency`, `historyConnectEvents` | `apps/backend/tests/conversations/citations_persisted_test.py`, `apps/backend/tests/conversations/duplicate_response_test.py` | `cd apps/backend && uv run pytest tests/conversations/citations_persisted_test.py tests/conversations/duplicate_response_test.py` |
| helpdesk workflow, memory, or ticket approval | `backend/helpdesk-workflow.md`, `backend/state-and-persistence.md` | `apps/backend/app/modules/helpdesk/internal/graph.py`, `apps/backend/app/modules/helpdesk/internal/memory.py`, `apps/backend/app/modules/tickets/api.py` | `build_helpdesk_workflow`, `FoundryMemoryProvider`, `create_ticket` | `apps/backend/tests/helpdesk/sources_event_test.py`, `apps/backend/tests/tenancy/memory_scope_test.py` | `cd apps/backend && uv run pytest tests/helpdesk/sources_event_test.py tests/tenancy/memory_scope_test.py` |
| oncall LangGraph approval or edit flow | `backend/oncall-graph.md` | `apps/backend/app/modules/oncall/internal/graph.py`, `apps/frontend/components/chat/GraphApproval.tsx` | `build_oncall_graph`, `InMemorySaver` | `apps/backend/tests/hitl/edit_roundtrip_test.py`, `apps/backend/tests/e2e/configured_mode_test.py` | `cd apps/backend && uv run pytest tests/hitl/edit_roundtrip_test.py tests/e2e/configured_mode_test.py` |
| platform MCP tools or hosted platform path | `backend/platform-ops.md`, `hosted-agents/hosted-agents.md` | `apps/backend/app/modules/platform_ops/internal/platform.py`, `apps/backend/app/modules/hosted/internal/hosted.py` | `platform_agent_proxy`, `stream_agui`, `SERVERS` | `apps/backend/tests/platform_ops/mcp_brokering_e2e_test.py`, `apps/backend/tests/hosted/platform_hosted_bridge_test.py` | `cd apps/backend && uv run pytest tests/platform_ops/mcp_brokering_e2e_test.py tests/hosted/platform_hosted_bridge_test.py` |
| tenancy, onboarding, tenant config, or admin APIs | `backend/tenancy-and-admin.md`, `backend/state-and-persistence.md` | `apps/backend/app/modules/tenancy/api.py`, `apps/backend/app/modules/tenancy/internal/tenant_store.py`, `apps/backend/app/modules/admin/api_admin.py` | `TenantRecord`, `require_domain`, `api_router` | `apps/backend/tests/tenancy/tenant_admin_e2e_test.py`, `apps/backend/tests/tenancy/tenant_resolution_test.py` | `cd apps/backend && uv run pytest tests/tenancy/tenant_admin_e2e_test.py tests/tenancy/tenant_resolution_test.py` |
| frontend domain routing, console behavior, or inline evidence UX | `frontend/frontend-overview.md`, `frontend/assurance-console.md` | `apps/frontend/components/console/AssuranceConsole.tsx`, `apps/frontend/components/console/MessageEvidence.tsx`, `apps/frontend/components/console/SourceViewer.tsx`, `apps/frontend/lib/citations.tsx` | `AssuranceConsole`, `makeAssistantMessage`, `CitationsProvider`, `SourceViewer` | `apps/frontend/scripts/verify-thread-citations.mjs`, `apps/frontend/scripts/verify-highlight.mjs` | `cd apps/frontend && node scripts/verify-thread-citations.mjs && node scripts/verify-highlight.mjs` |
| frontend proxy routes | `frontend/frontend-api-proxies.md` | `apps/frontend/app/api/copilotkit/[[...slug]]/route.ts`, `apps/frontend/app/api/source/[domain]/[name]/route.ts`, `apps/frontend/lib/auth/api.ts` | `GET`, `authedFetch` | `apps/frontend/scripts/verify-thread-citations.mjs` | `cd apps/frontend && node scripts/verify-thread-citations.mjs` |
| admin UI, tickets, evals pages | `frontend/admin-and-operations-ui.md` | `apps/frontend/components/admin/AdminUsers.tsx`, `apps/frontend/components/admin/Connections.tsx`, `apps/frontend/components/tickets/TicketsView.tsx` | `AdminUsers`, `Connections`, `TicketsView` | `cd e2e && npm test -- smoke.spec.ts` | `cd e2e && npm test -- smoke.spec.ts` |
| azd/Bicep deployment or ops scripts | `infrastructure/infra-and-deployment.md`, `infrastructure/scripts-and-runbooks.md` | `azure.yaml`, `infra/main.bicep`, `scripts/setup-entra.sh` | deployment hooks and azd wiring | repository docs plus targeted infra checks | inspect the owning page for the narrowest command |
| browser-level validation flows | `testing/end-to-end.md` | `e2e/playwright.config.ts`, `e2e/smoke.spec.ts`, `e2e/techdocs-acl.spec.ts` | Playwright projects and smoke flows | `e2e/smoke.spec.ts`, `e2e/techdocs-acl.spec.ts` | `cd e2e && npm test -- smoke.spec.ts` |

## Main sections

- `architecture/` — repository-wide topology and cross-system flows.
- `backend/` — FastAPI composition root, runtime domains, tenancy, knowledge, persistence, and tests.
- `frontend/` — Next.js shell, console, proxies, admin surfaces, and evidence UX.
- `hosted-agents/` — hosted packages and backend hosted bridges.
- `infrastructure/` — azd/Bicep deployment and operational scripts.
- `testing/` — browser-level end-to-end coverage.

## Fast validation shortcuts

- backend route or mount change → `cd apps/backend && uv run pytest tests/smoke/routes_snapshot_test.py`
- grounded retrieval, citation, or source-document change → `cd apps/backend && uv run pytest tests/grounded/framework_agent_test.py tests/knowledge/document_api_test.py`
- conversation persistence or evidence replay change → `cd apps/backend && uv run pytest tests/conversations/citations_persisted_test.py tests/conversations/duplicate_response_test.py`
- frontend inline evidence or source viewer change → `cd apps/frontend && node scripts/verify-thread-citations.mjs && node scripts/verify-highlight.mjs`
- browser UX or auth change → `cd e2e && npm test -- smoke.spec.ts`

## Backlog

- No evidence-backed backlog items remain from this update range.
