---
type: "Reference"
title: "Repository quickstart"
openwiki_generated: true
verified:
  - by: openwiki/0.4.3
    at: 2026-09-02T18:24:34.393Z
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-2c5d297c326a363e9ead1d50
    resource: repo://apps/backend/app/main.py
  - id: openwiki-source-65327b0f861b4603c2f5d09c
    resource: repo://apps/backend/app/modules/authoring/api.py
  - id: openwiki-source-8471982413cc31edc2dd25c1
    resource: repo://apps/backend/app/modules/authoring/public.py
  - id: openwiki-source-03a76265a5a9f4f77f7b7c42
    resource: repo://apps/backend/app/modules/grounded/internal/grounded.py
  - id: openwiki-source-f077d407912a802a7623d3fb
    resource: repo://apps/backend/app/modules/knowledge/api.py
  - id: openwiki-source-74f0378353aa7d7f1ff68604
    resource: repo://apps/backend/app/modules/knowledge/internal/document.py
  - id: openwiki-source-023bb6dfce299a081b60b13f
    resource: repo://apps/backend/app/modules/knowledge/internal/retrieval.py
  - id: openwiki-source-a16c6dc32621151f6c50580c
    resource: repo://apps/backend/app/modules/proposer/api.py
  - id: openwiki-source-2102f720b22ec35d1097a265
    resource: repo://apps/backend/app/modules/publication/api.py
  - id: openwiki-source-99c240eaac1ee437e606a4fc
    resource: repo://apps/backend/app/modules/publication/public.py
  - id: openwiki-source-e87f49bb471a66fa69f1e61c
    resource: repo://apps/backend/app/registry.py
  - id: openwiki-source-0c199bd66a1c04098baf7d94
    resource: repo://apps/backend/tests/registry/domain_registry_test.py
  - id: openwiki-source-c9df086641842f127fabca5d
    resource: repo://apps/backend/tests/smoke/routes_snapshot_test.py
  - id: openwiki-source-61b88fa07789f6d2b2c9d850
    resource: repo://apps/frontend/lib/domains.ts
  - id: openwiki-source-ccae8ff8ac19c71781e555d2
    resource: repo://apps/mcp/mcp_app/main.py
  - id: openwiki-source-23775c3de52f3ab95a13cb8b
    resource: repo://README.md
  - id: openwiki-source-7bed3702536945f710b73c89
    resource: repo://scripts/gates.py
generated: { by: "openwiki/0.4.3", at: "2026-09-02T18:24:34.393Z" }
---


# Repository quickstart

Start here only to decide **what to read next**. This page is intentionally a routing map, not a second README or a compressed architecture dump.

The repository has three runtime surfaces that matter before most changes:

- the FastAPI backend monolith mounts domain endpoints and shared HTTP routers from `apps/backend/app/main.py` and `apps/backend/app/registry.py`.[`apps/backend/app/main.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/main.py#L21-L29) [`apps/backend/app/main.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/main.py#L120-L140) [`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L250-L300)
- the frontend keeps its own contract-level domain registry in `apps/frontend/lib/domains.ts`, which drives navigation, `/d/[domain]` routing, and backend endpoint selection.[`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L1-L16) [`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L24-L41) [`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L43-L118)
- the MCP server is its own FastMCP app under `apps/mcp/mcp_app/main.py`, not a backend sub-route, but it reuses backend business seams such as the shared domain catalog and tenancy/knowledge surfaces.[`apps/mcp/mcp_app/main.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/mcp_app/main.py#L1-L27) [`apps/mcp/mcp_app/main.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/mcp_app/main.py#L102-L137) [`README.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/README.md#L98-L115)

## Read in this order for most tasks

1. **Find your surface and domain kind** in [Domain catalog, routing kinds, and frontend/backend parity](./architecture/domain-catalog-and-routing.md).
2. **Confirm the runtime boundary** in [Runtime topology across backend, frontend, MCP, and infra](./architecture/runtime-topology.md).
3. Then jump to the workflow or integration page that owns the behavior you are changing.
4. Before coding, pick the smallest matching gate from [Assurance gates, boundary tests, and change-safety signals](./testing/assurance-and-boundary-gates.md).

## Task routing map

| If you need to change... | Read this page first | Why this is the first owner | Concrete entrypoints to inspect next | Smallest useful validation next |
| --- | --- | --- | --- | --- |
| backend boot, route mounting, domain enablement, or shared-mode startup | [Runtime topology across backend, frontend, MCP, and infra](./architecture/runtime-topology.md) | `app.main` is thin by design and delegates live domain mounting to `mount_domains(app)` after tenancy/chat middleware wiring. | `apps/backend/app/main.py`, `apps/backend/app/registry.py` | `cd apps/backend && uv run pytest tests/smoke/routes_snapshot_test.py tests/registry/domain_registry_test.py` |
| adding or renaming a domain, changing a domain kind, or fixing frontend/backend drift | [Domain catalog, routing kinds, and frontend/backend parity](./architecture/domain-catalog-and-routing.md) | Backend runtime topology comes from shared domain catalog data, while the frontend mirrors ids/kinds/endpoints in `DOMAINS`. | `apps/backend/app/registry.py`, `apps/frontend/lib/domains.ts` | `cd apps/backend && uv run pytest tests/registry/domain_registry_test.py tests/smoke/routes_snapshot_test.py` |
| grounded `techdocs`/`selfwiki` answer flow, citations, retrieval, or source reopening | [Grounded answer and evidence flow](./workflows/grounded-answer-and-evidence.md) | Grounded domains share one mounted archetype and one evidence flow from retrieval to citation UI and document reopen. | `apps/backend/app/registry.py`, `apps/backend/app/modules/grounded/internal/grounded.py`, `apps/backend/app/modules/knowledge/internal/retrieval.py` | `cd apps/backend && uv run pytest tests/grounded/framework_agent_test.py tests/grounded/sources_message_id_test.py tests/knowledge/retrieval_acl_parity_test.py tests/knowledge/document_api_test.py tests/knowledge/document_access_test.py` |
| MCP auth/discovery, tools/resources/prompts/completion, or machine-facing evidence behavior | [Separate MCP server surface and its contracts](./integrations/mcp-server-surface.md) | MCP is a separate deployment and composition root, with its own protocol surface but shared backend business seams. | `apps/mcp/mcp_app/main.py` | inspect that page’s focused `apps/mcp/tests/*` gates first |
| authoring proposals, OKF changesets, review state, GitHub publication, or Azure DevOps publication | [Authoring, proposer, OKF changesets, and publication saga](./workflows/authoring-to-publication.md) | This flow is intentionally split into proposer, authoring, and publication boundaries, and only publication performs external writes. | backend `app/modules/proposer`, `app/modules/authoring`, `app/modules/publication` | inspect that page’s approval/publication contract tests first |
| deployment-mode behavior, local boot, demo mode, env wiring, or Azure deployment shape | [Configuration, local/dev modes, and deployment paths](./operations/configuration-and-deployment.md) | Runtime behavior differs across backend, web, and MCP services, and the README’s local/demo commands are the fastest ops entrypoint. | `README.md`, `azure.yaml`, `infra/` | run only the service boot or deployment check relevant to your surface |
| cross-boundary safety, import/routing drift, ACL fail-closed behavior, or “what proves this promise?” | [Assurance gates, boundary tests, and change-safety signals](./testing/assurance-and-boundary-gates.md) | The repository encodes many guarantees as merge-blocking gates rather than relying on architecture prose alone. | `.github/workflows/ci.yml`, `scripts/gates.py`, focused test modules | `python scripts/gates.py --list` then run the smallest matching gate |

## Fast mental model before editing code

Use these three facts to avoid most wrong-first-edits:

- `mount_domains(app)` walks the static backend topology and dispatches by `kind`, so route-shape changes usually belong in backend composition or the shared domain catalog, not in random feature modules.[`apps/backend/app/registry.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/app/registry.py#L250-L270)
- The frontend `DOMAINS` list is the UX contract mirror of those backend domains, including `kind`, `endpoint`, and whether a domain belongs in the main selector or only in the dock.[`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L24-L41) [`apps/frontend/lib/domains.ts`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/frontend/lib/domains.ts#L43-L118)
- The MCP app wires its registry from the same backend catalog and only then registers tools/resources/prompts/completion, so MCP domain exposure should be derived, not hardcoded locally.[`apps/mcp/mcp_app/main.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/mcp_app/main.py#L102-L137) [`apps/mcp/mcp_app/main.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/mcp_app/main.py#L139-L200)

## Where the README still helps

Use the repository `README.md` for product-level orientation, local boot commands, and the top-level distinction between the AG-UI web product and the separate MCP server surface.[`README.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/README.md#L12-L16) [`README.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/README.md#L19-L33) [`README.md`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/README.md#L117-L150)

If you already know your target behavior, prefer the owner pages linked above over rereading the README.

## Minimal pre-change checklist

- Confirm which surface you are changing: backend, frontend, MCP, or infra.
- Confirm whether the change is really about a **domain catalog/routing** decision, a **workflow** decision, an **integration** decision, or an **operations** decision.
- Read the owning page from the routing table.
- Run the smallest matching boundary gate before and after your change.

## Backlog

- No evidence-backed backlog items remain for this page in the current repository state.
