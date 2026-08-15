---
type: quickstart
title: OpenWiki quickstart
description: Entry point to the repository wiki, with a map of major systems, task routing, and focused validation guidance.
tags: [quickstart, navigation, wiki]
---

# OpenWiki quickstart

This wiki explains how Foundry Assured is built, how its runtime systems fit together, and where to look before changing code. The repository is a monorepo for:

- a **Next.js frontend**,
- a **FastAPI backend**,
- multiple **Foundry hosted agents**,
- **Azure infrastructure**,
- a **knowledge and wiki ingestion pipeline**,
- and an **assurance harness** that guards runtime and generated knowledge quality.

## Start here by goal

| If you want to change... | Read first | Then read | Focused validation |
| --- | --- | --- | --- |
| Overall architecture or deployment modes | [Repository architecture](architecture/overview.md) | [Infrastructure deployment](infrastructure/deployment.md) | `bicep build infra/main.bicep --stdout > /dev/null` |
| FastAPI composition, routes, or package ownership | [Backend application overview](backend/application-overview.md) | [Backend domains and endpoints](backend/domains-and-endpoints.md) | `uv run pytest eval/domain_registry_test.py eval/domains_api_test.py` |
| Auth, OBO, shared mode, or tenant scoping | [Backend auth and tenancy](backend/auth-and-tenancy.md) | [Admin and tenant APIs](backend/admin-and-tenant-apis.md) | `uv run pytest eval/tenant_resolution_test.py eval/domain_gate_test.py eval/memory_scope_test.py` |
| Helpdesk workflow or ticket escalation | [Helpdesk workflow](backend/helpdesk-workflow.md) | [Evaluations and tickets](backend/evaluations-and-tickets.md) | `uv run pytest eval/approval_mode_test.py eval/prompt_contract_test.py` |
| Grounded answers, citations, or ACL retrieval | [Grounded domains](backend/grounded-domains.md) | [Retrieval and ACL](backend/retrieval-and-acl.md) | `uv run pytest eval/retrieval_acl_parity_test.py eval/native_snippet_test.py` |
| Platform tools, MCP, or hosted Invocations bridge | [Platform domain](backend/platform-domain.md) | [Hosted platform](hosted-agents/platform-hosted.md) | `uv run pytest eval/mcp_registry_test.py eval/connection_tools_build_test.py eval/platform_hosted_bridge_test.py eval/hosted_build_test.py` |
| Prompt or AgentSchema definitions | [Declarative agent definitions](backend/agent-definitions.md) | [Security and fidelity gates](assurance/security-and-fidelity-gates.md) | `uv run pytest eval/prompt_contract_test.py` |
| Corpus, docbundles, or wiki ingestion | [Knowledge pipeline](backend/knowledge-pipeline.md) | [Security and fidelity gates](assurance/security-and-fidelity-gates.md) | `uv run pytest eval/docbundle_contract_test.py eval/wiki_fidelity_test.py eval/wiki_freshness_test.py` |
| Generic chat UI or domain console behavior | [Frontend application overview](frontend/application-overview.md) | [Frontend domain console](frontend/domain-console.md) | `npm run lint && npm run typecheck` |
| Admin pages, tenant UI, tickets page, or evals page | [Frontend admin, evals, and tickets](frontend/admin-evals-and-tickets.md) | [Admin and tenant APIs](backend/admin-and-tenant-apis.md) | `npm run lint && npm run typecheck` |
| Demo replay mode | [Frontend demo mode](frontend/demo-mode.md) | [End-to-end tests and validation](testing/end-to-end-and-validation.md) | `npm run demo` |
| Hosted-agent containers | [Hosted agents overview](hosted-agents/overview.md) | domain-specific hosted page | backend bridge tests plus deploy workflow review |
| CI, deploy, release, or wiki regeneration automation | [Automation and release](operations/automation-and-release.md) | [Evaluation harness](assurance/evaluation-harness.md) | match local commands to the workflow steps |

## Major sections

### Architecture

- [Repository architecture](architecture/overview.md)

Use this when you need the cross-system picture: domains, live versus hosted paths, and deployment modes.

### Backend

- [Backend application overview](backend/application-overview.md)
- [Backend auth and tenancy](backend/auth-and-tenancy.md)
- [Backend domains and endpoints](backend/domains-and-endpoints.md)
- [Helpdesk workflow](backend/helpdesk-workflow.md)
- [Grounded domains](backend/grounded-domains.md)
- [Retrieval and ACL](backend/retrieval-and-acl.md)
- [Platform domain](backend/platform-domain.md)
- [Declarative agent definitions](backend/agent-definitions.md)
- [Admin and tenant management APIs](backend/admin-and-tenant-apis.md)
- [Evaluations and tickets](backend/evaluations-and-tickets.md)
- [Knowledge pipeline](backend/knowledge-pipeline.md)

### Frontend

- [Frontend application overview](frontend/application-overview.md)
- [Frontend domain console](frontend/domain-console.md)
- [Frontend admin, evals, and tickets pages](frontend/admin-evals-and-tickets.md)
- [Frontend demo mode](frontend/demo-mode.md)

### Hosted agents

- [Hosted agents overview](hosted-agents/overview.md)
- [Hosted helpdesk agent](hosted-agents/helpdesk-hosted.md)
- [Hosted selfwiki and cockpit agents](hosted-agents/selfwiki-and-cockpit.md)
- [Hosted platform agent](hosted-agents/platform-hosted.md)

### Infrastructure and operations

- [Infrastructure deployment](infrastructure/deployment.md)
- [Dedicated mode infrastructure](infrastructure/dedicated-mode.md)
- [Infrastructure identity and access](infrastructure/identity-and-access.md)
- [Automation and release workflows](operations/automation-and-release.md)

### Assurance and validation

- [Evaluation harness](assurance/evaluation-harness.md)
- [Security and fidelity gates](assurance/security-and-fidelity-gates.md)
- [End-to-end tests and validation recipes](testing/end-to-end-and-validation.md)

## Key concepts to keep in mind

1. **Domains are config-driven**. Frontend and backend registries must stay aligned.
2. **Live and hosted are different runtime forms**. Do not assume feature parity without checking the hosted pages.
3. **Shared mode is a provider seam**. Most runtime code should use `tenant_config()` and related helpers rather than branching manually on deployment mode.
4. **Grounded domains depend on retrieval and ingest together**. A bug may live in runtime retrieval, upstream corpus shape, or generated wiki adaptation.
5. **Assurance code is product code**. Eval and fidelity workflows are part of how the repository stays safe to change.

## Minimal local navigation recipes

- Want to understand why a UI page exists: start in the matching frontend page, then follow its proxy route to the backend API page.
- Want to add or restore a domain: check `apps/frontend/lib/domains.ts` and `apps/backend/app/domains.py` via [Repository architecture](architecture/overview.md) and [Backend domains and endpoints](backend/domains-and-endpoints.md).
- Want to debug citations or missing documents: read [Grounded domains](backend/grounded-domains.md), then [Retrieval and ACL](backend/retrieval-and-acl.md), then [Knowledge pipeline](backend/knowledge-pipeline.md).
- Want to change deploy automation: read [Infrastructure deployment](infrastructure/deployment.md) and [Automation and release](operations/automation-and-release.md) together.

## Backlog

None. The current wiki covers the substantial runtime services, APIs, workflows, infrastructure packaging paths, automation, and validation systems evidenced in the repository.
