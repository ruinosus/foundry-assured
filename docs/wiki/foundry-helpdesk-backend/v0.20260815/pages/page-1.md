# Backend wiki quickstart

This wiki documents **only** `apps/backend`. It is organized around the backend's runtime systems rather than the source tree so you can move quickly from a change intention to the owning subsystem, route family, invariants, and focused validation.

## Start here

- Runtime composition and the four backend domains: Backend overview
- Mounted endpoints, hosted twins, and JSON APIs: Backend API surface
- Entra auth, OBO, tenant resolution, onboarding, and domain entitlement: Auth and tenancy
- Declarative prompt loading and `AGENTS_DIR` behavior: Prompt and agent-definition system
- Triage → retrieve → resolve → escalate workflow: Helpdesk workflow
- Grounded `cockpit` and `selfwiki` path: Grounded domains
- Tool-driven `platform` domain and MCP brokering: Platform domain and MCP brokering
- Global runtime settings, hosted bridges, caches, and ops endpoints: Operations and runtime behavior
- Docbundle ingestion and backend-owned wiki pipeline: Knowledge pipeline and docbundle contract
- Test harness and assurance gates: Evaluation and assurance

## Backend mental model

The backend is a FastAPI app with one thin composition root in `app.main`, one domain registry in `app.domains`, and four live domains:

- `helpdesk`: AG-UI workflow
- `cockpit`: grounded SSE Q and A
- `selfwiki`: grounded SSE Q and A over repo wiki content
- `platform`: tool-driven AG-UI agent

Shared-mode multitenancy is layered underneath those domains by auth dependencies, tenant resolution, and per-domain entitlement gates rather than by duplicating route trees. The grounded and platform paths are request-time systems; they should be understood together with auth and tenancy, not in isolation.

## Task routing

| Change intent | Read first | Key source owners | Focused validation |
|---|---|---|---|
| Add or change a live domain mount | Backend overview, Backend API surface | `app/main.py`, `app/domains.py` | `uv run python -m eval.domain_registry_test` |
| Debug auth, OBO, or tenant 403s | Auth and tenancy | `app/core/auth.py`, `app/core/tenant.py`, `app/core/onboarding.py` | `uv run python -m eval.tenant_resolution_test && uv run python -m eval.domain_gate_test` |
| Change onboarding or tenant admin behavior | Auth and tenancy, Backend API surface | `app/api/tenant.py`, `app/core/onboarding.py`, `app/core/tenant_store.py` | `uv run python -m eval.onboarding_guard_test && uv run python -m eval.domains_api_test` |
| Change prompt YAML, guardrails, or prompt boot behavior | Prompt and agent-definition system | `app/agents/definitions.py`, `app/agents/prompts.py`, `agents/helpdesk/*` | `uv run python -m eval.prompt_contract_test` |
| Change helpdesk workflow or escalation | Helpdesk workflow | `app/workflow/*.py`, `app/tools/tickets.py` | `uv run python -m eval.prompt_contract_test && uv run python -m eval.memory_scope_test` |
| Change retrieval, citations, or grounded synthesis | Grounded domains | `app/services/retrieval.py`, `app/services/grounded.py`, `app/domains.py` | `uv run python -m eval.retrieval_shape_test` |
| Debug per-user grounded ACL behavior | Grounded domains, Auth and tenancy | `app/services/retrieval.py`, `app/services/grounded.py` | `uv run python -m eval.retrieval_acl_parity_test && uv run python -m eval.grounded_archetype_roundtrip_test` |
| Add or debug MCP servers, tools, or connection policy | Platform domain and MCP brokering | `app/agents/mcp/registry.py`, `app/agents/mcp/tools.py`, `app/core/tenant_store.py` | `uv run python -m eval.mcp_registry_test && uv run python -m eval.connection_tools_build_test && uv run python -m eval.approval_mode_test` |
| Debug hosted bridges or runtime caches | Operations and runtime behavior | `app/services/hosted.py`, `app/api/chat.py`, `app/main.py` | `uv run python -m eval.platform_hosted_bridge_test && uv run python -m eval.hosted_build_test` |
| Change bundle ingest, manifest handling, or wiki pipeline | Knowledge pipeline and docbundle contract | `app/knowledge/ingest_docbundles.py`, `app/knowledge/adapt_openwiki.py`, `app/knowledge/docbundle_schema.py`, `app/knowledge/wiki_builder.py` | `uv run python -m eval.docbundle_contract_test && uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend` |
| Understand which tests protect a subsystem | Evaluation and assurance | `apps/backend/eval/*` | pick the invariant batch from that page |

## Validation strategy

Prefer focused checks over broad sweeps:

- Domain and route wiring: `uv run python -m eval.domain_registry_test`
- Prompt behavior: `uv run python -m eval.prompt_contract_test`
- Tenant gating: `uv run python -m eval.tenant_resolution_test`
- Grounded retrieval contract: `uv run python -m eval.retrieval_shape_test`
- Platform tool policy: `uv run python -m eval.mcp_registry_test`
- Bundle contract and fidelity: `uv run python -m eval.docbundle_contract_test && uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend`

## Backlog

None. The current wiki scope is limited to `apps/backend`, and the documented backend systems all have dedicated pages.
