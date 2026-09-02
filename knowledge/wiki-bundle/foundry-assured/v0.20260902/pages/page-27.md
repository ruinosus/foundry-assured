---
type: "Reference"
title: "Assurance gates, boundary tests, and change-safety signals"
openwiki_generated: true
verified:
  - by: openwiki/0.4.3
    at: 2026-09-02T18:24:34.393Z
sources:
  - id: openwiki-source-164e2da859b5277df81c7d94
    resource: repo://.github/workflows/ci.yml
  - id: openwiki-source-eeaefc0cb2fb961af84ed3d2
    resource: repo://apps/backend/eval/wiki_fidelity_test.py
  - id: openwiki-source-06a08c73d0af0f03d834e9d4
    resource: repo://apps/backend/tests/architecture/module_graph_test.py
  - id: openwiki-source-3c2bda00f5113e232f5e3ba6
    resource: repo://apps/backend/tests/architecture/proposer_read_only_test.py
  - id: openwiki-source-6f340732bb6af0831abf4345
    resource: repo://apps/backend/tests/platform_ops/mcp_discovery_auth_test.py
  - id: openwiki-source-69b731b27d0f30436ec6d9d2
    resource: repo://apps/backend/tests/publication/github_publication_test.py
  - id: openwiki-source-2be151d3e1fb0ecd0c5dba94
    resource: repo://apps/mcp/tests/client_surface_test.py
  - id: openwiki-source-7bed3702536945f710b73c89
    resource: repo://scripts/gates.py
generated: { by: "openwiki/0.4.3", at: "2026-09-02T18:24:34.393Z" }
---
# Assurance gates, boundary tests, and change-safety signals

This repository treats many architectural promises as **merge-blocking gates**, not as comments or ADR prose. The main CI workflow runs lint plus a long sequence of offline, deterministic tests from `apps/backend`, and it explicitly frames those steps as the checks that must pass on every PR and push to `main`. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L1-L18) [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L34-L39)

For local development, `scripts/gates.py` does not maintain its own hand-written gate list. It parses `.github/workflows/ci.yml`, derives executable `run:` steps and their working directories, skips setup steps like `uv sync` and `npm ci`, and can either list or run the same gates locally. By default it runs only the offline deterministic jobs (`backend` and `mcp-app`), while `--all` includes the rest. That keeps local green meaningfully aligned with CI green. [`gates.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/gates.py#L1-L22) [`gates.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/gates.py#L35-L50) [`gates.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/gates.py#L53-L79) [`gates.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/gates.py#L100-L136)

Organizationally, the useful unit is not a test directory. It is the **guarantee** being protected: boundary integrity, route parity, security fail-closed behavior, protocol-surface filtering, and authoring/publication contract fidelity.

## Guarantee: the test shelf and local runner match the real merge gates

The first assurance invariant is meta-assurance: developers should not get a false sense of safety from running a partial or stale local checklist. The repo addresses that by making the CI workflow the source of truth and having `scripts/gates.py` derive local execution from it, including step-level `working-directory` overrides. It also marks missing local executables as loud skips rather than false passes. [`gates.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/gates.py#L53-L79) [`gates.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/gates.py#L100-L136)

That matters because the CI workflow is broad. Beyond lint, it includes gates for whole-document ACL, wiki shelf fidelity, OKF authoring profile behavior, GitHub and Azure DevOps publication flows, route snapshots, import-linter contracts, module graph drift, MCP discovery/auth/drift/observability, tenancy isolation, and more. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L44-L107) [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L135-L191) [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L220-L280)

## Guarantee: architectural boundaries stay explicit as code moves

The architecture gates are aimed at a specific failure mode: refactors that keep behavior superficially working while quietly introducing new coupling.

### Inter-module edges are recorded and new coupling fails loudly

`module_graph_test.py` builds a dependency graph by assigning every Python file under `app/` to a target module, parsing imports from the AST, and comparing the resulting cross-module edge set against a fixture. A file with no module assignment fails the run, and a new edge fails the run while naming the importing file that introduced it. This is intentionally a pre-directory or refactor-honesty gate, not just a style check. [`module_graph_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/architecture/module_graph_test.py#L1-L19) [`module_graph_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/architecture/module_graph_test.py#L33-L45) [`module_graph_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/architecture/module_graph_test.py#L107-L149) [`module_graph_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/architecture/module_graph_test.py#L152-L199)

The CI workflow pairs that with two related static-boundary checks:

- import-linter contracts as the architecture gate of record, and
- an import-linter coverage test so a missing contract entry cannot create a silent hole. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L171-L184)

Together these are the main change-safety signals for modular-monolith refactors described in the runtime topology page: the system keeps shared seams such as the domain catalog stable while resisting accidental new cross-module reach-through. `runtime-topology.md`

### The proposer remains structurally read-only

`proposer_read_only_test.py` turns the ADR promise around the proposer into an AST-enforced rule. It scans `app/modules/proposer`, forbids imports or calls to a named set of resource-writing functions, detects direct collection writes like `client.agents.create_version(...)`, catches alias-based writes, and even blocks `getattr(..., "delete")`-style indirection. It explicitly allows read/inference operations and explains that optimization jobs are not publication. [`proposer_read_only_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/architecture/proposer_read_only_test.py#L1-L18) [`proposer_read_only_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/architecture/proposer_read_only_test.py#L28-L49) [`proposer_read_only_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/architecture/proposer_read_only_test.py#L62-L106) [`proposer_read_only_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/architecture/proposer_read_only_test.py#L109-L149)

This is a good example of the repository’s testing posture: it does not just test outputs, it tests that a component cannot even gain the wrong kind of dependency without tripping a gate.

## Guarantee: route and surface parity regressions are caught as topology changes

A second class of change-safety signal is route-surface parity: code moves must not silently drop or add externally visible endpoints.

The CI workflow includes a route-snapshot gate that boots the backend under `self_hosted` and `shared` profiles in separate interpreters and compares `method + path` against a recorded fixture. The workflow comments describe it as the safety net for the modular-monolith refactor and as protection against endpoints disappearing because a router import or inclusion was forgotten. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L163-L169)

Related architecture gates also reinforce that route parity depends on boot wiring, not just function existence:

- `module_invocations_test` checks `python -m ...` entrypoints in workflows and scripts still resolve after moves. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L223-L229)
- `filesystem_anchors_test` forbids fragile `parents[N]` path counting that previously broke under module moves. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L193-L199)

In practice, these gates protect the composition-root boundaries documented in the runtime topology page: the backend must keep mounting domain routes correctly, while MCP remains a separate composition root rather than being silently reintroduced into backend routing. `runtime-topology.md` `runtime-topology.md`

## Guarantee: citations and wiki claims stay ingest-safe and auditable

The repository’s wiki fidelity gates exist because generated or adapted documentation becomes model-facing knowledge. The key invariant is not “nice links”; it is that page citations resolve to real repository sources and that stale bundles cannot remain committed unnoticed.

`eval/wiki_fidelity_test.py` applies the same fidelity logic used by the wiki builder to externally generated bundles. It loads bundle pages from `knowledge/wiki-bundle/<component>/<version>/pages`, computes a report with `_fidelity_report`, enforces the configured `_fidelity_floor`, and rejects any bundle with even one worktree citation. When `--version` is omitted it uses numeric-segment ordering so date-stamped bundles sort correctly against semver-like names. [`wiki_fidelity_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/eval/wiki_fidelity_test.py#L1-L20) [`wiki_fidelity_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/eval/wiki_fidelity_test.py#L40-L62) [`wiki_fidelity_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/eval/wiki_fidelity_test.py#L64-L103)

The CI workflow complements that with two broader shelf/format gates:

- `eval.wiki_shelf_test` remeasures every committed bundle, not just the newest generated one. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L80-L87)
- `tests.knowledge.wiki_frontmatter_test` and `tests.knowledge.bundle_frontmatter_roundtrip_test` protect OKF provenance in generated pages while ensuring frontmatter is preserved in files but removed before retrieval indexing. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L118-L129)

This is the gate family that keeps the citation discipline required by the grounded-answer and evidence flow honest: model-facing documentation must remain source-auditable rather than becoming a stale or hallucinated secondary corpus. `tenancy-areas-and-access-control.md`

## Guarantee: access-control behavior is fail-closed, including whole-document reads

Security-sensitive gates are organized around fail-closed invariants, especially for document access.

The CI workflow contains a cluster of knowledge gates that together verify:

- whole-document access fails closed under mutation,
- the HTTP `GET /source` contract returns the right auth/error behavior and blocks caching/SSRF hazards,
- authorized chunk counting uses the identity header correctly,
- `session` containers cannot declare content whose access policy they do not actually enforce, and
- source-declared access metadata survives into the index while frontmatter stays out of retrieval text. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L47-L70)

Those gates matter because the access-control model is layered across authentication, shared-mode tenant resolution, domain entitlement, authoring-area scope, role checks, and document ACL. The tenancy page makes explicit that whole-document reads and retrieval-fed model context are separate enforcement paths and that both must fail closed before content reaches either callers or models. `tenancy-areas-and-access-control.md` `tenancy-areas-and-access-control.md`

A useful boundary-testing pattern here is that many of these are not simple unit tests. They are mutation or round-trip contract tests built because “nobody calls the unsafe path” is not considered sufficient evidence.

## Guarantee: MCP discovery and MCP protocol surfaces cannot drift into unsafe behavior

The MCP-related gates split into two different invariants: the **endpoint discovery/control plane** must authenticate and egress safely, and the **runtime protocol surface** must only expose authorized tools, prompts, resources, and completion results.

### Discovery authenticates late, through approved tenant-local seams

`mcp_discovery_auth_test.py` exercises `discover_endpoint` across public, connection-backed, and OBO auth modes. It proves that public endpoints send no auth header provider; connection credentials are not resolved until session use; credential resolution is memoized per session; the connection reference is looked up within the current tenant; the broker only receives the approved Foundry connection id and approved origin; bad or incompatible connection cases raise `MCP_AUTH_NOT_AVAILABLE` without calling discovery; and OBO uses an allowlisted audience scope. [`mcp_discovery_auth_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/platform_ops/mcp_discovery_auth_test.py#L1-L17) [`mcp_discovery_auth_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/platform_ops/mcp_discovery_auth_test.py#L36-L102) [`mcp_discovery_auth_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/platform_ops/mcp_discovery_auth_test.py#L104-L167)

In CI, that test sits beside the rest of the MCP discovery and binding gates: egress isolation, direct-endpoint approval behavior, classification, conformity, canonical hashing, drift quarantine, stale-review fail-closed behavior, secret canaries, adversarial discovery limits, content-free stable errors, observability, and tenant-isolated connections. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L220-L280)

This is the executable version of the MCP server contract described in the integration page: MCP remains a separate machine-facing surface, but it still reuses shared tenancy and authorization policy rather than inventing its own. `mcp-server-surface.md`

### The real MCP client surface is filtered by authorization, not just annotated

`apps/mcp/tests/client_surface_test.py` is the protocol-surface gate. It builds the real ASGI app with `build_app()`, swaps in a static token verifier so the test stays offline, replaces the domain registry and authorized-document seam with controlled fakes, and then uses a real `fastmcp.Client` over in-process streamable HTTP to observe what two callers can list and read. [`client_surface_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/tests/client_surface_test.py#L1-L17) [`client_surface_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/tests/client_surface_test.py#L92-L119) [`client_surface_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/tests/client_surface_test.py#L122-L143) [`client_surface_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/tests/client_surface_test.py#L157-L189)

Its assertions pin the externally visible contract:

- a `Reader` sees only the read tools, sees prompts, sees the document resource template, can read the document, and gets domain completion suggestions; [`client_surface_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/tests/client_surface_test.py#L197-L222)
- a caller with no roles sees no tools, no prompts, no templates, direct document reads are refused, completion returns no suggestions, and authorized content does not leak in the refusal path. [`client_surface_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/mcp/tests/client_surface_test.py#L224-L239)

That test matters because the security boundary here is partly in **listing behavior**. Unauthorized surfaces are filtered out of discovery, not merely made to error when invoked. The integration page explicitly points to this as the end-to-end proof that list filtering and direct reads behave as intended. `mcp-server-surface.md` `tenancy-areas-and-access-control.md`

## Guarantee: publication only materializes approved, safe, idempotent changes

Publication tests are contract tests around approval, projection safety, replay semantics, and area isolation.

`github_publication_test.py` builds a `GitHubPublicationService` with fake approval and gateway seams and then walks the whole approval sequence. It verifies that publication is not a replay on first run; each GitHub native tool is presented for approval before execution; the expected tool sequence is `search_pull_requests`, `create_branch`, `push_files`, `create_pull_request`, then `pull_request_read`; approved documents are normalized to LF; target paths are deterministic; branches are derived stably from the approved hash; only a safe PR projection is persisted; identical idempotency keys replay the completed publication without creating new side effects; a changed content hash cannot reuse that key; exact `Approver` role is required; area isolation is fail-closed; persisted state contains no tokens or raw remote responses; and invalid PR projections are rejected. [`github_publication_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/publication/github_publication_test.py#L24-L53) [`github_publication_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/publication/github_publication_test.py#L93-L149) [`github_publication_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/publication/github_publication_test.py#L151-L205) [`github_publication_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/publication/github_publication_test.py#L207-L259) [`github_publication_test.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/apps/backend/tests/publication/github_publication_test.py#L260-L340)

The CI workflow runs that GitHub contract test together with:

- the HTTP publication contract,
- native Toolbox approval loop tests,
- infra-gated GitHub smoke,
- Azure DevOps gateway/publication/smoke tests, and
- post-merge reconciliation/materialization tests. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L135-L152)

This gate family is the executable counterpart to the authoring/publication access model: publication is area-scoped, approval-bound, and designed to materialize only already approved content through sanitized, idempotent adapters. `tenancy-areas-and-access-control.md`

## Guarantee: authoring and publication document contracts fail high before merge-time materialization

Another major assurance family is the OKF authoring profile. The CI workflow separates this into multiple gates rather than one opaque test:

- envelope, identity, and publication state,
- references, tenancy, and immutable revisions,
- writes and `cannotWrite`,
- schemas and ticket fixtures,
- legacy compatibility and migration,
- multi-document ChangeSet proposal and review,
- actor/timestamp rules. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L98-L117)

The important testing strategy here is decomposition by invariant. A regression can tell maintainers whether they broke syntax/identity, tenant-safe reference resolution, write permissions, or migration behavior instead of collapsing all of that into “authoring failed.” That matches the repository’s broader pattern: enforce publication and authoring as **contract surfaces** whose safety properties are checked before any external publication adapter or knowledge ingest sees the result.

## Practical reading of the signals

When changing this codebase, the most meaningful green signals are these:

- **module graph / import-linter green**: your refactor did not introduce new architectural coupling;
- **route snapshot green**: you did not silently change the backend’s externally visible HTTP surface;
- **wiki fidelity green**: model-facing documentation still cites real, current code and can be ingested safely;
- **document ACL gates green**: content still fails closed before users or models see it;
- **MCP discovery and client-surface green**: machine-facing integrations still authenticate, filter, and disclose only what policy allows;
- **OKF and publication gates green**: authoring artifacts and publication adapters still honor approval, tenancy, idempotency, and safe projection contracts.

That is the repository’s main assurance philosophy: every important boundary has a focused executable witness, and the witnesses are wired into the same CI workflow that decides whether code can merge. [`ci.yml`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/.github/workflows/ci.yml#L1-L18) [`gates.py`](https://github.com/ruinosus/foundry-assured/blob/18595cf77fa56dad04a5e646bc5dae9bcae7f6fa/scripts/gates.py#L82-L136)
