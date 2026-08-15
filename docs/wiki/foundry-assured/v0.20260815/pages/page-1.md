This wiki documents the entire `foundry-assured` repository as one system: backend, frontend, hosted agents, infrastructure, operational scripts, and end-to-end tests. The repository’s central idea is not just “an app with agents”; it is a repo that packages agent experiences together with measurable assurance gates for grounding, access control, and generated wiki fidelity.`README.md` `README.md` `docs/adr/ADR-016-openwiki-closes-the-freshness-loop.md`

## Start here by intent

| If you want to change… | Read this page first | Key source entrypoints | Focused validation |
| --- | --- | --- | --- |
| overall architecture or deployment modes | architecture/overview.md | `apps/backend/app/main.py`, `apps/frontend/lib/domains.ts`, `infra/main.bicep` | `cd apps/backend && uv run python -m eval.docbundle_contract_test` |
| FastAPI composition, route mounting, or backend service boundaries | backend/overview.md | `apps/backend/app/main.py`, `apps/backend/app/domains.py`, `apps/backend/app/api/__init__.py` | `cd apps/backend && uv run python -m eval.domain_registry_test` |
| helpdesk workflow, approval, or memory | backend/workflow-helpdesk.md | `apps/backend/app/workflow/*` | `cd apps/backend && uv run python -m eval.approval_mode_test` |
| grounded retrieval, citations, or ACL trimming | backend/grounded-domains.md | `apps/backend/app/services/grounded.py`, `apps/backend/app/services/retrieval.py` | `cd apps/backend && uv run python -m eval.access_control_test` |
| platform tools or hosted platform bridging | backend/platform-domain.md | `apps/backend/app/agents/platform.py`, `apps/backend/app/services/hosted.py`, `apps/hosted-platform/main.py` | `cd apps/backend && uv run python -m eval.platform_hosted_bridge_test` |
| auth, OBO, or shared-mode resolution | backend/auth-and-tenancy.md | `apps/backend/app/core/auth.py`, `apps/backend/app/core/tenant.py` | `cd apps/backend && uv run python -m eval.credential_wiring_test` |
| tenant onboarding, connections, or domain entitlements | backend/tenant-control-plane.md | `apps/backend/app/api/tenant.py`, `apps/backend/app/core/tenant_store.py` | `cd apps/backend && uv run python -m eval.tenant_store_test` |
| Graph-backed admin APIs, tickets, or eval summaries | backend/admin-and-operations.md | `apps/backend/app/services/graph.py`, `apps/backend/app/api/*` | `cd apps/backend && uv run python -m eval.connection_ops_test` |
| wiki/docbundle ingest or assurance thresholds | backend/knowledge-and-assurance.md | `apps/backend/app/knowledge/*`, `apps/backend/eval/*` | `cd apps/backend && uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend` |
| Next.js layout, routing, or auth shell | frontend/overview.md | `apps/frontend/app/*`, `apps/frontend/components/shell/AppShell.tsx` | `cd apps/frontend && npm run typecheck` |
| CopilotKit console, evidence panel, or hosted toggle UX | frontend/assurance-console.md | `apps/frontend/components/console/AssuranceConsole.tsx` | `cd e2e && npm test` |
| proxy route handlers or token forwarding | frontend/proxies-and-request-flow.md | `apps/frontend/app/api/*`, `apps/frontend/lib/auth/api.ts` | `cd e2e && npm test` |
| admin, tickets, or evals pages | frontend/admin-evals-and-tickets.md | `apps/frontend/components/{admin,evals,tickets}/*` | `cd apps/frontend && npm run lint` |
| hosted agent packaging | hosted-agents/overview.md | `apps/hosted-*`, `azure.yaml` | `cd apps/backend && uv run python -m eval.hosted_build_test` |
| Azure resources or RBAC | infra/overview.md and infra/identity-and-rbac.md | `infra/*.bicep`, `scripts/hook-postdeploy.sh` | `./scripts/up-all.sh --provision-only` |
| deployment scripts, hooks, or prompt publishing | operations/scripts-and-deployment.md | `scripts/*.sh`, `azure.yaml` | `./scripts/bootstrap.sh` |
| backend assurance suites or browser E2E | testing-and-evals/overview.md and testing-and-evals/e2e.md | `apps/backend/eval/*`, `e2e/*` | `cd e2e && npm test` |

## Main sections

- architecture/overview.md — whole-repo map and cross-system flows
- backend/overview.md — FastAPI composition root and service boundaries
- frontend/overview.md — Next.js shell, routes, and auth shape
- hosted-agents/overview.md — hosted packaging strategy and protocol split
- infra/overview.md — Azure resource topology and azd/Bicep output surfaces
- operations/scripts-and-deployment.md — deployment automation chain
- testing-and-evals/overview.md — proof-oriented tests and assurance gates

## Repository concepts worth learning early

### Domain registry

Both backend and frontend are registry-driven around the same four domains: `helpdesk`, `cockpit`, `selfwiki`, and `platform`. The frontend registry controls labels and route behavior; the backend registry controls runtime kind and mounting.[`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/frontend/lib/domains.ts#L28-L95) [`apps/backend/app/domains.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/domains.py#L63-L99)

### Shared-mode control plane

Shared deployment mode adds a tenant-record subsystem with onboarding, per-tenant config, connection references, and domain entitlements. It is the most important subsystem to understand before changing multi-tenant behavior.[`apps/backend/app/core/auth.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/core/auth.py#L77-L94) [`apps/backend/app/api/tenant.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/app/api/tenant.py#L86-L100)

### Assurance gates

The repo’s generated wiki, retrieval, and access-control behavior are all guarded by executable checks, especially the docbundle contract test, wiki fidelity test, access-control test, and Playwright E2E suite.[`apps/backend/eval/docbundle_contract_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/docbundle_contract_test.py#L1-L27) [`apps/backend/eval/wiki_fidelity_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/wiki_fidelity_test.py#L1-L20) [`apps/backend/eval/access_control_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/access_control_test.py#L1-L15) [`e2e/smoke.spec.ts`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/e2e/smoke.spec.ts#L123-L132)

## Suggested reading order

1. architecture/overview.md
2. backend/overview.md
3. frontend/overview.md
4. the domain-specific backend page for your area
5. the corresponding hosted/infra/operations/testing page if your change crosses runtime boundaries

## Backlog

None currently. The inspected repo surfaces were documentable from source and tests in this run.