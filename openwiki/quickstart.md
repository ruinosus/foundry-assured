---
type: guide
title: OpenWiki quickstart
description: Entry point for the repository wiki. Use this page to route from an engineering task or change area to the canonical wiki page, source-owned subsystem, focused tests, and smallest useful validation step.
tags: [quickstart, navigation]
---

# OpenWiki quickstart

This wiki covers the full `foundry-assured` repository: backend, frontend, hosted agents, infrastructure, scripts, and end-to-end tests. The repository is a domain-driven monorepo for an engineering concierge that combines grounded retrieval, a workflow agent, a tool-driven ops agent, hosted-agent deployments, and an assurance loop that treats citations, ACLs, and evals as product features rather than afterthoughts ([README.md](https://github.com/ruinosus/foundry-assured/blob/08e078d7f2b6febbc5135f0b7928b5a204c667e3/README.md#L1-L34), [README.md](https://github.com/ruinosus/foundry-assured/blob/08e078d7f2b6febbc5135f0b7928b5a204c667e3/README.md#L155-L172)).

Start with the architecture map if you need global orientation, then branch into the canonical subsystem page for the thing you are changing:

- Repository map: [architecture/overview](./architecture/overview.md)
- Domain catalog contract: [architecture/domains-and-registry](./architecture/domains-and-registry.md)
- Auth and OBO model: [architecture/auth-and-identity](./architecture/auth-and-identity.md)
- Backend composition root: [backend/overview](./backend/overview.md)
- Frontend runtime: [frontend/app-and-runtime](./frontend/app-and-runtime.md)
- Infra and deployment orchestration: [infra-and-ops/infra](./infra-and-ops/infra.md) and [infra-and-ops/azd-and-hooks](./infra-and-ops/azd-and-hooks.md)
- Test and assurance evidence: [testing-and-assurance/overview](./testing-and-assurance/overview.md)

## Task routing

| Change intent | Read first | Then read | Focused evidence | Minimal validation |
| --- | --- | --- | --- | --- |
| Add or change a domain | [architecture/domains-and-registry](./architecture/domains-and-registry.md) | [backend/overview](./backend/overview.md), [frontend/app-and-runtime](./frontend/app-and-runtime.md) | registry tests and browser smoke | verify `/d/<domain>` plus backend mount behavior |
| Change sign-in, roles, or OBO | [architecture/auth-and-identity](./architecture/auth-and-identity.md) | [backend/tenancy](./backend/tenancy.md) | tenant resolution and browser sign-in flows | one authenticated browser flow plus one role-gated action |
| Change helpdesk workflow or approval | [backend/helpdesk](./backend/helpdesk.md) | [backend/admin-and-tickets](./backend/admin-and-tickets.md) | smoke helpdesk flow and tickets path | ask helpdesk, approve/reject escalation, inspect `/tickets` |
| Change grounded retrieval or citations | [backend/knowledge-retrieval](./backend/knowledge-retrieval.md) | [backend/grounded-domains](./backend/grounded-domains.md) | retrieval ACL parity, grounded round-trip, cockpit ACL browser test | verify structured citations and A/B ACL behavior |
| Change corpus ingest, ACL stamping, or bundle schema | [backend/knowledge-ingestion](./backend/knowledge-ingestion.md) | [backend/wiki-and-docbundles](./backend/wiki-and-docbundles.md) | ACL stamp test and schema validation | run ingest path and inspect resulting index/schema |
| Change platform tools or MCP RBAC | [backend/platform-ops](./backend/platform-ops.md) | [backend/tenancy](./backend/tenancy.md) | per-tool RBAC and connection-build tests | verify one read and one write-intent tool path |
| Change hosted bridges or hosted agent behavior | [backend/hosted-bridges-and-evals](./backend/hosted-bridges-and-evals.md) | [hosted-agents/responses-agents](./hosted-agents/responses-agents.md) or [hosted-agents/platform-invocations](./hosted-agents/platform-invocations.md) | hosted bridge tests | one hosted UI run plus bridge-specific test |
| Change admin or tenant control plane | [backend/admin-and-tickets](./backend/admin-and-tickets.md) | [frontend/api-proxies-and-admin](./frontend/api-proxies-and-admin.md) | admin/tenant tests and role checks | one admin page action and one tenant API action |
| Change deployment assets or azd flow | [infra-and-ops/infra](./infra-and-ops/infra.md) | [infra-and-ops/azd-and-hooks](./infra-and-ops/azd-and-hooks.md), [infra-and-ops/scripts-and-e2e](./infra-and-ops/scripts-and-e2e.md) | hook behavior plus e2e smoke after deploy | `azd up` or targeted hook/script rerun |
| Change prompt assets or agent definitions | [backend/agentdefs](./backend/agentdefs.md) | [infra-and-ops/scripts-and-e2e](./infra-and-ops/scripts-and-e2e.md) | prompt contract checks and runtime restart path | restart backend and exercise affected agent |

## Main sections

### Architecture

- [overview](./architecture/overview.md): top-level runtime and deployment map.
- [domains-and-registry](./architecture/domains-and-registry.md): frontend/backend domain parity, hosted twins, entitlement, hidden domains.
- [auth-and-identity](./architecture/auth-and-identity.md): MSAL, backend bearer validation, OBO, roles, onboarding guard.

### Backend

- [overview](./backend/overview.md): composition root, module boundaries, router inclusion, mount loop.
- [agentdefs](./backend/agentdefs.md): AgentSchema prompt assets and publishing.
- [helpdesk](./backend/helpdesk.md): workflow, memory, escalation, approval invariants.
- [grounded-domains](./backend/grounded-domains.md): shared grounded serving path for cockpit and selfwiki.
- [knowledge-ingestion](./backend/knowledge-ingestion.md): corpus upload, KB/index lifecycle, ACL stamping.
- [knowledge-retrieval](./backend/knowledge-retrieval.md): native/direct retrieval, ACL headers, docKey decode.
- [wiki-and-docbundles](./backend/wiki-and-docbundles.md): OpenWiki/deep-wiki adaptation and bundle contract.
- [tenancy](./backend/tenancy.md): deployment-mode seam, tenant store, enabled domains, memory scope.
- [platform-ops](./backend/platform-ops.md): MCP registry, RBAC, credential brokering.
- [hosted-bridges-and-evals](./backend/hosted-bridges-and-evals.md): hosted proxy paths and eval APIs.
- [admin-and-tickets](./backend/admin-and-tickets.md): Graph admin APIs, tenant APIs, tickets.

### Frontend

- [app-and-runtime](./frontend/app-and-runtime.md): generic console, auth flow, citations, demo mode.
- [api-proxies-and-admin](./frontend/api-proxies-and-admin.md): Next route handlers and admin UI proxy layer.

### Hosted agents

- [responses-agents](./hosted-agents/responses-agents.md): hosted helpdesk, cockpit, selfwiki.
- [platform-invocations](./hosted-agents/platform-invocations.md): hosted platform over Invocations and Toolbox.

### Infrastructure and operations

- [infra](./infra-and-ops/infra.md): Azure topology and output-to-runtime mapping.
- [azd-and-hooks](./infra-and-ops/azd-and-hooks.md): service graph, build-time env push, postdeploy reconciliation.
- [scripts-and-e2e](./infra-and-ops/scripts-and-e2e.md): operator scripts, demo flow, Playwright suites.

### Testing and assurance

- [overview](./testing-and-assurance/overview.md): evidence families, assurance pillars, and how to pick the smallest meaningful proof.

## Navigation tips

- If a behavior depends on deployment mode, read [architecture/auth-and-identity](./architecture/auth-and-identity.md) and [backend/tenancy](./backend/tenancy.md) together.
- If a behavior depends on citations or retrieval, pair [backend/knowledge-retrieval](./backend/knowledge-retrieval.md) with [frontend/app-and-runtime](./frontend/app-and-runtime.md).
- If a change touches hosted mode, always check both the hosted service page and the backend bridge page.
- If a page mentions a test family, the narrowest useful validation is usually there before a full browser or deploy run.

## Backlog

- None. The current wiki scope covers the full repository requested in `openwiki/INSTRUCTIONS.md`, including backend, frontend, infra, hosted agents, scripts, and e2e.
