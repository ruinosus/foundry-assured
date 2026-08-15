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
| Overall architecture or deployment modes | Repository architecture | Infrastructure deployment | `bicep build infra/main.bicep --stdout > /dev/null` |
| FastAPI composition, routes, or package ownership | Backend application overview | Backend domains and endpoints | `uv run pytest eval/domain_registry_test.py eval/domains_api_test.py` |
| Auth, OBO, shared mode, or tenant scoping | Backend auth and tenancy | Admin and tenant APIs | `uv run pytest eval/tenant_resolution_test.py eval/domain_gate_test.py eval/memory_scope_test.py` |
| Helpdesk workflow or ticket escalation | Helpdesk workflow | Evaluations and tickets | `uv run pytest eval/approval_mode_test.py eval/prompt_contract_test.py` |
| Grounded answers, citations, or ACL retrieval | Grounded domains | Retrieval and ACL | `uv run pytest eval/retrieval_acl_parity_test.py eval/native_snippet_test.py` |
| Platform tools, MCP, or hosted Invocations bridge | Platform domain | Hosted platform | `uv run pytest eval/mcp_registry_test.py eval/connection_tools_build_test.py eval/platform_hosted_bridge_test.py eval/hosted_build_test.py` |
| Prompt or AgentSchema definitions | Declarative agent definitions | Security and fidelity gates | `uv run pytest eval/prompt_contract_test.py` |
| Corpus, docbundles, or wiki ingestion | Knowledge pipeline | Security and fidelity gates | `uv run pytest eval/docbundle_contract_test.py eval/wiki_fidelity_test.py eval/wiki_freshness_test.py` |
| Generic chat UI or domain console behavior | Frontend application overview | Frontend domain console | `npm run lint && npm run typecheck` |
| Admin pages, tenant UI, tickets page, or evals page | Frontend admin, evals, and tickets | Admin and tenant APIs | `npm run lint && npm run typecheck` |
| Demo replay mode | Frontend demo mode | End-to-end tests and validation | `npm run demo` |
| Hosted-agent containers | Hosted agents overview | domain-specific hosted page | backend bridge tests plus deploy workflow review |
| CI, deploy, release, or wiki regeneration automation | Automation and release | Evaluation harness | match local commands to the workflow steps |

## Major sections

### Architecture

- Repository architecture

Use this when you need the cross-system picture: domains, live versus hosted paths, and deployment modes.

### Backend

- Backend application overview
- Backend auth and tenancy
- Backend domains and endpoints
- Helpdesk workflow
- Grounded domains
- Retrieval and ACL
- Platform domain
- Declarative agent definitions
- Admin and tenant management APIs
- Evaluations and tickets
- Knowledge pipeline

### Frontend

- Frontend application overview
- Frontend domain console
- Frontend admin, evals, and tickets pages
- Frontend demo mode

### Hosted agents

- Hosted agents overview
- Hosted helpdesk agent
- Hosted selfwiki and cockpit agents
- Hosted platform agent

### Infrastructure and operations

- Infrastructure deployment
- Dedicated mode infrastructure
- Infrastructure identity and access
- Automation and release workflows

### Assurance and validation

- Evaluation harness
- Security and fidelity gates
- End-to-end tests and validation recipes

## Key concepts to keep in mind

1. **Domains are config-driven**. Frontend and backend registries must stay aligned.
2. **Live and hosted are different runtime forms**. Do not assume feature parity without checking the hosted pages.
3. **Shared mode is a provider seam**. Most runtime code should use `tenant_config()` and related helpers rather than branching manually on deployment mode.
4. **Grounded domains depend on retrieval and ingest together**. A bug may live in runtime retrieval, upstream corpus shape, or generated wiki adaptation.
5. **Assurance code is product code**. Eval and fidelity workflows are part of how the repository stays safe to change.

## Minimal local navigation recipes

- Want to understand why a UI page exists: start in the matching frontend page, then follow its proxy route to the backend API page.
- Want to add or restore a domain: check `apps/frontend/lib/domains.ts` and `apps/backend/app/domains.py` via Repository architecture and Backend domains and endpoints.
- Want to debug citations or missing documents: read Grounded domains, then Retrieval and ACL, then Knowledge pipeline.
- Want to change deploy automation: read Infrastructure deployment and Automation and release together.

## Backlog

None. The current wiki covers the substantial runtime services, APIs, workflows, infrastructure packaging paths, automation, and validation systems evidenced in the repository.
