# Backend wiki quickstart

This wiki covers the backend only: `apps/backend` and backend-owned assurance material. It is organized around runtime systems and change surfaces rather than the raw directory tree.

## Start here by intent

- Backend architecture and route composition: Backend overview
- Live helpdesk workflow and approval flow: Helpdesk workflow
- Grounded cockpit and selfwiki paths: Grounded domains
- Auth, OBO, shared-mode tenancy, and memory scope: Auth and tenancy
- Tool-driven platform domain and MCP governance: Platform domain
- Declarative prompt loading and prompt contracts: Prompt system
- HTTP APIs and route contracts: Backend API surface
- Wiki/docbundle generation, ingest, ACL stamping, and freshness/fidelity: Knowledge pipeline
- Assurance thresholds and validation suites: Evaluation and assurance
- Runtime lifecycle, config layers, and validation routing: Operations and runtime
- Hosted agent transport bridges: Hosted bridges

## High-level map

The backend has three main runtime families:

1. **Live domains** mounted by `app/domains.py`
   - `helpdesk`: workflow domain
   - `cockpit` and `selfwiki`: grounded domains
   - `platform`: tool domain
2. **Ordinary HTTP APIs** under `app/api/*`
   - health, identity, tickets, evals, admin, tenant, hosted twins
3. **Knowledge and assurance tooling**
   - prompt composition, wiki/docbundle generation and ingest, ACL stamping, eval gates

## Task routing

| Change intent | Read first | Primary source entrypoints | Focused tests | Minimal validation |
| --- | --- | --- | --- | --- |
| Add or change a backend domain | Backend overview, Grounded domains, Platform domain | `app/domains.py`, `app/agents/*`, `app/services/grounded.py` | `eval.domain_registry_test` | `uv run python -m eval.domain_registry_test` |
| Modify helpdesk workflow or approval logic | Helpdesk workflow | `app/workflow/graph.py`, `app/workflow/escalation.py`, `app/workflow/agents.py` | `eval.prompt_contract_test`, `eval.approval_mode_test` | `uv run python -m eval.prompt_contract_test` |
| Change shared auth or tenant resolution | Auth and tenancy, Backend API surface | `app/core/auth.py`, `app/core/tenant.py`, `app/api/tenant.py` | `eval.tenant_resolution_test`, `eval.domain_gate_test` | `uv run python -m eval.tenant_resolution_test` |
| Change tenant admin/config/connection APIs | Backend API surface | `app/api/tenant.py`, `app/core/tenant_store.py` | `eval.domains_api_test`, `eval.tenant_scope_test` | `uv run python -m eval.domains_api_test` |
| Change prompt documents or prompt loading | Prompt system | `app/agents/prompts.py`, `app/agents/definitions.py`, `apps/backend/agents/helpdesk/` | `eval.prompt_contract_test` | `uv run python -m eval.prompt_contract_test` |
| Change retrieval, citations, or ACL trimming | Grounded domains, Knowledge pipeline | `app/services/grounded.py`, `app/services/retrieval.py`, `app/knowledge/acl_setup.py` | `eval.retrieval_acl_parity_test`, `eval.native_snippet_test` | `uv run python -m eval.retrieval_acl_parity_test` |
| Change ingestion or wiki/docbundle adapters | Knowledge pipeline | `app/knowledge/ingest_docbundles.py`, `app/knowledge/wiki_builder.py`, `app/knowledge/adapt_openwiki.py` | `eval.docbundle_contract_test`, `eval.wiki_fidelity_test` | `uv run python -m eval.docbundle_contract_test` |
| Add MCP tool/server support | Platform domain, Backend API surface | `app/agents/mcp/registry.py`, `app/agents/mcp/tools.py`, `app/api/tenant.py` | `eval.mcp_registry_test`, `eval.connection_tools_build_test` | `uv run python -m eval.mcp_registry_test` |
| Change hosted-agent transport | Hosted bridges | `app/api/chat.py`, `app/services/hosted.py` | `eval.platform_hosted_bridge_test`, `eval.hosted_build_test` | `uv run python -m eval.platform_hosted_bridge_test` |
| Understand repo assurance gates | Evaluation and assurance | `eval/assurance.yaml`, `eval/*` | depends on subsystem | start with page-linked suite |

## Main concepts to keep in mind

- **Deployment mode is the primary seam.** Runtime code should prefer `tenant_config()` and auth helpers over branching directly on environment state.
- **Prompt source is declarative.** Runtime prompt constants are derived from AgentSchema documents and guarded by prompt-contract tests.
- **Grounded answers depend on ingestion state.** Retrieval correctness and ACL behavior require the knowledge pipeline and retrieval pipeline to stay aligned.
- **Hosted twins are not the same as live domains.** They share domain intent but use separate transport bridges and have their own operational risks.

## Backlog

None. The current backend-only inventory is covered by the pages above based on inspected source and eval surfaces.
