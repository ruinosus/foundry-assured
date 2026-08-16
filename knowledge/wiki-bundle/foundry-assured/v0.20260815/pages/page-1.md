# OpenWiki quickstart

This wiki covers the full `foundry-assured` repository: backend, frontend, hosted agents, infrastructure, scripts, and end-to-end tests. The repository is a domain-driven monorepo for an engineering concierge that combines grounded retrieval, a workflow agent, a tool-driven ops agent, hosted-agent deployments, and an assurance loop that treats citations, ACLs, and evals as product features rather than afterthoughts (README.md, README.md).

Start with the architecture map if you need global orientation, then branch into the canonical subsystem page for the thing you are changing:

- Repository map: architecture/overview
- Domain catalog contract: architecture/domains-and-registry
- Auth and OBO model: architecture/auth-and-identity
- Backend composition root: backend/overview
- Frontend runtime: frontend/app-and-runtime
- Infra and deployment orchestration: infra-and-ops/infra and infra-and-ops/azd-and-hooks
- Test and assurance evidence: testing-and-assurance/overview

## Task routing

| Change intent | Read first | Then read | Focused evidence | Minimal validation |
| --- | --- | --- | --- | --- |
| Add or change a domain | architecture/domains-and-registry | backend/overview, frontend/app-and-runtime | registry tests and browser smoke | verify `/d/<domain>` plus backend mount behavior |
| Change sign-in, roles, or OBO | architecture/auth-and-identity | backend/tenancy | tenant resolution and browser sign-in flows | one authenticated browser flow plus one role-gated action |
| Change helpdesk workflow or approval | backend/helpdesk | backend/admin-and-tickets | smoke helpdesk flow and tickets path | ask helpdesk, approve/reject escalation, inspect `/tickets` |
| Change grounded retrieval or citations | backend/knowledge-retrieval | backend/grounded-domains | retrieval ACL parity, grounded round-trip, cockpit ACL browser test | verify structured citations and A/B ACL behavior |
| Change corpus ingest, ACL stamping, or bundle schema | backend/knowledge-ingestion | backend/wiki-and-docbundles | ACL stamp test and schema validation | run ingest path and inspect resulting index/schema |
| Change platform tools or MCP RBAC | backend/platform-ops | backend/tenancy | per-tool RBAC and connection-build tests | verify one read and one write-intent tool path |
| Change hosted bridges or hosted agent behavior | backend/hosted-bridges-and-evals | hosted-agents/responses-agents or hosted-agents/platform-invocations | hosted bridge tests | one hosted UI run plus bridge-specific test |
| Change admin or tenant control plane | backend/admin-and-tickets | frontend/api-proxies-and-admin | admin/tenant tests and role checks | one admin page action and one tenant API action |
| Change deployment assets or azd flow | infra-and-ops/infra | infra-and-ops/azd-and-hooks, infra-and-ops/scripts-and-e2e | hook behavior plus e2e smoke after deploy | `azd up` or targeted hook/script rerun |
| Change prompt assets or agent definitions | backend/agentdefs | infra-and-ops/scripts-and-e2e | prompt contract checks and runtime restart path | restart backend and exercise affected agent |

## Main sections

### Architecture

- overview: top-level runtime and deployment map.
- domains-and-registry: frontend/backend domain parity, hosted twins, entitlement, hidden domains.
- auth-and-identity: MSAL, backend bearer validation, OBO, roles, onboarding guard.

### Backend

- overview: composition root, module boundaries, router inclusion, mount loop.
- agentdefs: AgentSchema prompt assets and publishing.
- helpdesk: workflow, memory, escalation, approval invariants.
- grounded-domains: shared grounded serving path for cockpit and selfwiki.
- knowledge-ingestion: corpus upload, KB/index lifecycle, ACL stamping.
- knowledge-retrieval: native/direct retrieval, ACL headers, docKey decode.
- wiki-and-docbundles: OpenWiki/deep-wiki adaptation and bundle contract.
- tenancy: deployment-mode seam, tenant store, enabled domains, memory scope.
- platform-ops: MCP registry, RBAC, credential brokering.
- hosted-bridges-and-evals: hosted proxy paths and eval APIs.
- admin-and-tickets: Graph admin APIs, tenant APIs, tickets.

### Frontend

- app-and-runtime: generic console, auth flow, citations, demo mode.
- api-proxies-and-admin: Next route handlers and admin UI proxy layer.

### Hosted agents

- responses-agents: hosted helpdesk, cockpit, selfwiki.
- platform-invocations: hosted platform over Invocations and Toolbox.

### Infrastructure and operations

- infra: Azure topology and output-to-runtime mapping.
- azd-and-hooks: service graph, build-time env push, postdeploy reconciliation.
- scripts-and-e2e: operator scripts, demo flow, Playwright suites.

### Testing and assurance

- overview: evidence families, assurance pillars, and how to pick the smallest meaningful proof.

## Navigation tips

- If a behavior depends on deployment mode, read architecture/auth-and-identity and backend/tenancy together.
- If a behavior depends on citations or retrieval, pair backend/knowledge-retrieval with frontend/app-and-runtime.
- If a change touches hosted mode, always check both the hosted service page and the backend bridge page.
- If a page mentions a test family, the narrowest useful validation is usually there before a full browser or deploy run.

## Backlog

- None. The current wiki scope covers the full repository requested in `openwiki/INSTRUCTIONS.md`, including backend, frontend, infra, hosted agents, scripts, and e2e.
