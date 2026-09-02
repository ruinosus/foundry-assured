# ADR-017 — The backend is organized by business domain, and the boundaries are checked by CI

- **Status:** Proposed
- **Date:** 2026-08-15
- **Context:** [`apps/backend/app/`](../../apps/backend/app),
  [`apps/backend/app/domains.py`](../../apps/backend/app/domains.py),
  [`apps/backend/app/core/auth.py`](../../apps/backend/app/core/auth.py),
  [`apps/backend/app/core/tenant_store.py`](../../apps/backend/app/core/tenant_store.py),
  the consolidated spec `2026-08-15-modular-monolith-consolidated-spec.md`
- **Related:** [ADR-018](./ADR-018-no-ahp-for-now.md) decides the orchestration question this
  ADR deliberately leaves out of the module list

## Context

`apps/backend` is 5.951 lines of Python organized by **technical layer** —
`app/{api,services,agents,workflow,core,knowledge,tools}`. No directory corresponds to a
business concept. "Helpdesk" lives in `workflow/` plus `agents/prompts.py` plus
`tools/tickets.py` plus `api/tickets.py` plus part of `services/`. "Tenancy" lives in
`core/tenant*.py` plus `api/tenant.py` plus `core/onboarding.py`. `services/` holds five
responsibilities from five different domains.

The layering is also already broken in one place the type checker cannot see:
`app/core/tenant_store.py:13` imports `app.agents.mcp.registry.SERVERS`, while every file in
`app/agents` imports `app/core`. A cycle, held together by import order.

**The real import graph, measured before deciding anything** (AST walk over `app/**/*.py`,
each file assigned to its target module, edges deduplicated):

| from | to | via |
|---|---|---|
| COMPOSITION | agentdefs, grounded, helpdesk, hosted, platform_ops, shared, tenancy | `main.py`, `domains.py` |
| admin | shared | `api/admin.py`, `api/me.py`, `services/graph.py` |
| evaluation | shared, **tenancy** | `api/evals.py`, `services/foundry_evals.py` |
| grounded | agentdefs, **hosted**, knowledge, shared, tenancy | `services/grounded.py`, `agents/*.py` |
| helpdesk | agentdefs, shared, tenancy, tickets | `workflow/*.py` |
| hosted | **COMPOSITION**, shared, tenancy | `api/chat.py`, `services/hosted.py` |
| knowledge | shared, **tenancy** (5 files) | `services/retrieval.py`, `agents/secure_search.py`, `knowledge/*.py` |
| platform_ops | agentdefs, **grounded**, shared, tenancy | `agents/platform.py`, `agents/mcp/tools.py` |
| **shared** | **tenancy** | `core/auth.py` |
| tenancy | **platform_ops**, shared | `core/tenant_store.py`, `api/tenant.py` |
| tickets | shared | `api/tickets.py` |

Every `.py` file under `app/` maps to exactly one destination; the walk reported no unmapped
file. **32 edges across 11 nodes.** The bolded edges are the ones nobody had written down.

The walk is not a one-off script: it lives at
[`tests/architecture/module_graph_test.py`](../../apps/backend/tests/architecture/module_graph_test.py),
carries the file→module map above as its `MAP`, and runs in CI. It fails on a **new**
cross-module edge (naming the file that introduced it) and on any file with no module
assigned. `import-linter` can only guard directories that already exist; until Phase 3
creates them, this answers the same question against the plan.

## Decision

**Reorganize `apps/backend/app` into ten domain modules, each with an explicit public surface
and private internals, over a minimal shared kernel and a single composition root — and make
`import-linter` fail the build when a boundary is crossed.**

Three layers, and the dependency rule is the whole design:

```
composition (main.py, registry.py)  →  may import any module's public
modules/*                           →  app.shared + app.modules.<other>.public only
shared/                             →  nothing inside the app
```

The ten modules: `tenancy`, `admin`, `knowledge`, `helpdesk`, `grounded`, `platform_ops`,
`tickets`, `hosted`, `evaluation`, `agentdefs`. Each is a bounded context, not a layer. The
test applied to every file was one question — *what business is this?* If the answer is a
domain noun, it is a module; if it is "everybody's" (settings, request identity, telemetry),
it is `shared/`; if it is "nobody's, it just wires things", it is the composition root.

Inter-module communication stays **direct, in-process, through `public`**. No event bus: the
current coupling is synchronous and works, and introducing events would be a behavior change.

The post-merge publication saga adds the intentional edge `publication → foundry.public`.
`publication` owns merge confirmation, the idempotent operation journal and compensation order;
`foundry` remains the sole owner of the official SDK calls that create and delete agent, skill
and toolbox versions. Moving those calls into `publication` would duplicate the SDK boundary,
while moving the saga into `foundry` would mix ChangeSet lifecycle with resource management.
The graph fixture records this edge and import-linter still forbids access to `foundry.internal`.

**`agentdefs`** is the module that owns every declarative agent definition — `prompts.py` and
`definitions.py`, and from the spec's Phase 3.5 also the approval policy and per-tool role
gates. The spec's first revision called it `prompts` and described it as a re-export; with
`definitions.py` inside it, that name would lie. The documents themselves
(`apps/backend/agents/helpdesk/` [renamed to `agents/assured/` on 2026-08-24]) **do not move** — their path is a deployment contract
(ADR-014's Azure Files mount at `/mnt/agents`), not an implementation detail.

### What the measured graph forced us to change

The graph found three things the spec's first revision got wrong. All three are structural, and
two of them would have failed CI on the day the contract was switched on.

**1. `shared → tenancy`: `auth.py` is two things glued together.** The spec moves
`app/core/auth.py` wholesale into `shared/` in Phase 2 and enables the "shared imports no
modules" contract in the same phase. That fails immediately. `auth.py` carries six imports of
`app.core.tenant*` — including `resolve_tenant()`, described in its own docstring as the
"authorization choke point", plus tenant-store construction and provider registration at boot.
One of them already carries the comment `# local import avoids a cycle`. Being lazy does not
help: `import-linter` walks the AST and sees imports inside functions.

Decision: **split the file.** `shared/auth.py` keeps token validation, claims, `has_role`,
`current_user`, `auth_dependencies` — request identity, genuinely cross-cutting. Tenant
resolution, store construction and provider registration move to `tenancy`. The composition
root wires the two. This is a prerequisite of Phase 2, not a follow-up.

**2. `hosted → COMPOSITION`: `_domain_deps` is in the wrong place.** `api/chat.py` imports
`_domain_deps` from `app.domains`; once `api/chat.py` is `hosted/api.py` and `domains.py` is
the composition root, a module imports composition and the layer contract fails.

Decision: **`_domain_deps` moves to `tenancy.public`.** It is `auth_dependencies()` plus, in
shared mode, the per-tenant entitlement gate (`require_domain`, ADR-010) — that is the tenancy
domain, not wiring. `hosted → tenancy.public` and `registry → tenancy.public` are both already
legitimate edges.

**3. The list of "expected legitimate dependencies" was substantially wrong.** The spec
predicted `helpdesk → knowledge/tickets/prompts`, `grounded → knowledge/prompts`,
`platform_ops → prompts`, `hosted → tenancy`. The measurement adds five nobody listed:
`knowledge → tenancy` (five files), `evaluation → tenancy`, `grounded → hosted`,
`platform_ops → grounded` (it reuses `PerRequestAgent`), and `helpdesk → tenancy`. The
contracts in `importlinter.toml` are written from the measured graph, never from the prose.

### The cycle

`tenancy → platform_ops` exists because `tenant_store.py` validates connection references
against the MCP server catalog. `SERVERS` is data of the platform domain, so it lives in
`platform_ops/public.py`; `tenancy` does not import `platform_ops`; the composition root
injects the catalog at boot. Moving `SERVERS` into `shared/` is forbidden — it is not
cross-cutting, it is one domain's data.

### Enforcement

`importlinter.toml`, run as a required CI step, with three contract families: the three-layer
rule (C1), one `forbidden` contract per module making its `internal/` private to everyone else
(C2, ten of them), and the independence contracts that encode the domain decisions above (C3).
A contract loosened to make the build pass is a change to this ADR, and must be argued here.

`CLAUDE.md` gains Rule #7: new code goes **inside** an existing module or creates a new one
with `public`/`internal`; cross-module imports go through `public`; run `uv run lint-imports`
before committing.

## What this ADR deliberately does not decide

The consolidated spec's first revision also proposed an `orchestration` module — ports and
adapters over agent runtimes. That is **not** among the ten modules, and the reasoning is in
[ADR-018](./ADR-018-no-ahp-for-now.md). Briefly: its concrete deliverable was moving 24 lines
of real code behind five ports plus a stub for a runtime that is not in the repository. The
boundary work in this ADR stands on its own and does not depend on that decision.

## Alternatives considered

- **Keep the technical layering and just break the cycle.** Cheapest, and leaves the actual
  complaint untouched: a developer asked to change helpdesk behavior still opens five
  directories. Rejected — the cycle is a symptom.
- **Modules without `public`/`internal`.** Directories by domain, imports unrestricted. Gets
  the navigation win and none of the enforcement: within a month something imports a neighbor's
  private helper and the boundary is folklore again. Rejected — the point is that CI holds the
  line, not that the folders look right.
- **An event bus between modules.** Real decoupling, and a behavior change: ordering, failure
  semantics and debuggability all move. The current coupling is synchronous and works.
  Rejected for this change; a candidate follow-up if a module ever needs to fan out.
- **Put `auth.py` in `shared/` unsplit and grant it an exception in the contract.** One line of
  TOML instead of a refactor. It also makes `shared` depend on a domain permanently, which is
  the one rule that makes the other two layers meaningful. Rejected — the exception would be
  load-bearing.
- **`prompts` as the module name.** Familiar, and wrong once `definitions.py` and the approval
  policy live there. Rejected in favor of `agentdefs`; recorded here so the rename is a
  decision, not a drift.

## Consequences

- **+** A business change starts in one directory. The module list is the domain list.
- **+** The boundary is machine-checked, so it survives contributors who never read this ADR.
- **+** The cycle dies, and `auth.py` stops being the file where authentication and tenancy
  are the same thing.
- **+** Telemetry gets a natural dimension: every span carries `app.module`, so dashboards
  align to the same boundaries `import-linter` enforces.
- **−** The refactor touches nearly every file in `app/` as an import change. Reviewing it means
  trusting the mechanical checks (route snapshot, AG-UI fixtures, performance baseline) more
  than reading the diff.
- **−** Splitting `auth.py` is the one place where "pure move, no logic change" does not hold.
  It is a small, real refactor inside a change whose whole premise is that nothing else moves,
  and it must be reviewed as such.
- **−** `git log --follow` is needed to trace history across the move. `git mv` throughout keeps
  that working; nothing else does.
- **⚠** Ten `forbidden` contracts is verbose TOML that grows with every module. That is the
  cost of the rule being explicit rather than conventional.

## Recorded edges: the five modules that depend on `foundry.chat_client`

`tests/architecture/module_graph_test.py` flagged five new edges — `helpdesk`, `grounded`,
`platform_ops`, `builder` and `knowledge` all now import `foundry`. They are intended, and the
justification the gate asks for is this:

`FoundryChatClient` was being constructed **five times**, once inside each of those modules, with
byte-identical arguments. Five constructions are not merely duplication: they are five places where
each agent decides on its own what to instrument. The ROI panel showed the bill — one domain with
656 recorded tokens and every other domain at zero, because only one path remembered to call
`record_usage`. Fixing the paths one at a time would have left the structure intact and guaranteed
that the *next* agent would be born outside the accounting, which is how the bug was born.

So the edges buy a real reduction: **five constructions become one**, and measuring becomes a
property of talking to the model rather than of each agent remembering. One edge was also
*removed* (`builder -> tenancy`), which is the shape of coupling moving to one place rather than
growing. `tests/conversations/usage_seam_test.py` forbids a sixth loose construction.

The middleware is handed to `foundry` by the composition root rather than imported, because
`conversations` already imports `foundry` and the reverse edge would close a cycle that
`import-linter` refuses. That is the same inversion `main.py` already uses for
`tenancy.set_server_catalog(...)` — the composition root is the one place allowed to know both
sides.

## Recorded edge: `admin` depends on `tenancy` for the caller's area context

`GET /me` remains in `admin` because it projects the caller's identity and App Roles for the
administrative interface. Its area list, however, cannot be computed there: `tenancy` owns tenant
resolution, the tenant store and the intersection between validated Entra groups and active areas.
The endpoint therefore calls `tenancy.public.authorized_areas` and returns only that projection.

This edge keeps one authorization decision instead of reproducing group-to-area logic in `admin`.
It does not grant authority from the selected `X-Area-ID`; tenancy revalidates that header against
the same resolved set on every area-scoped request. The dependency follows the ADR rule by crossing
only through `public.py`, and the reverse edge does not exist.

## Recorded edges: `authoring` projects the modules that own factual resources

The authoring catalog is a bounded context because its business decision is transversal: present a
single, tenant-and-area-authorized observation without becoming a second operational registry. It
depends on `foundry`, `formflow`, `usecases` and `tenancy` only through their `public.py` surfaces;
`okf` supplies stable validation errors and `shared` supplies request roles. The composition root
mounts its HTTP router.

These edges do not transfer ownership. Agents, knowledge bases, skills and toolboxes remain in
Foundry/Search; FormFlows and copilots remain documents; use cases remain projections over Foundry
metadata; connections remain tenancy references. `authoring` materializes and sorts one ephemeral
snapshot, hashes it, paginates it and reports unavailable sources as gaps. It has no resource store,
SDK client or resource declaration of its own, and no reverse edge points back to it.

Conformidade por fase acrescenta uma quinta dependência, `authoring → platform_ops`, também somente
por `platform_ops.public`. O módulo de autoria não reimplementa descoberta, drift ou classificação
MCP: quando uma revisão contém `mcp-binding`, ele chama `evaluate_mcp_binding`, cujo domínio dono é
`platform_ops`, e persiste apenas a decisão sanitizada no relatório imutável. Sem binding, o import é
lazy e a capacidade não é inicializada. A direção inversa continua inexistente.

A decisão humana acrescenta `authoring → audit`, somente por `audit.public`. `authoring` continua
dono do agregado, da revisão e do armazenamento da decisão; `audit` continua dono da trilha
append-only. A gravação do evento ocorre antes da transição e sua falha bloqueia aprovação ou
rejeição, pois uma decisão sem recibo deixaria o estado publicado sem prova de ator e correlação. O
evento contém decisão, revisão, hash e metadados mínimos da razão, nunca o documento ou a razão
integral. A dependência inversa não existe e o HITL de tools permanece um mecanismo distinto.

## Recorded edges: five modules depend on `conversations` so that measuring is uniform

A second batch of intended edges — `hosted`, `oncall` and `deepcall` now import `conversations`,
joining the composition root and the domains that already did. The justification the graph gate
asks for:

The product runs agents through **four different runtimes**, and each has its own natural place to
hang instrumentation. Because each was built at a different time, the recording was born in four
places, and what existed on one path did not exist on another. Measured: only one of the four
recorded everything, and the least-instrumented surface of all was `/foundry-agent/{name}` — the
agent a **user** creates through the wizard, which is the surface the product exists to offer.

The edges buy convergence on **one destination with per-runtime entry points**, which is the
opposite of a second accounting:

| runtime | entry point | why that one |
|---|---|---|
| agent-framework | `ChatMiddleware` via the single chat-client factory | the framework's own seam |
| Responses SSE (hosted) | one recording call in the shared stream function | all three hosted routes pass through it |
| LangChain / LangGraph | `BaseCallbackHandler.on_llm_end` | LangChain's own observability surface (ADR-020) |
| per-request agents | `context_providers` on the shared `PerRequestAgent` | the proxy platform, builder and shared-mode grounded already cross |

Every one of them calls the **same** `record_usage`. Two numbers answering the same question
diverge without erroring — this repository already lived that when `wiki_builder` kept a private
copy of the price table. `tests/architecture/instrumentation_matrix_test.py` is the gate that keeps
the convergence honest: a new agent surface declares what it records, or CI fails.

### `helpdesk -> grounded`: the ACL-aware retrieval provider

One more intended edge. `grounded` owns `GroundedRetrieval`, a `ContextProvider` that wraps the
ACL-aware `retrieve()` seam, and `helpdesk` now uses it in place of the framework's
`AzureAISearchContextProvider`.

The reason is a measured gap, not a preference. The framework's provider covers grounding and
citation but does **not** send `x-ms-query-source-authorization` — the per-user ACL header (zero
occurrences in its 998-line module). With it, `helpdesk` was the only grounded domain that did
**not** trim per document, while `techdocs` and `selfwiki` did; and the reference count — the main
input to the Agent Assisted Hours formula — died there.

That is the whole justification for keeping any hand-written retrieval at all. The SSE loop around
it in the `grounded` domains is not a gap, it is accumulation; the gap is one HTTP header. Wrapping
`retrieve()` in the framework's own extension point is the same move `StoredHistoryProvider` already
made — `HistoryProvider` *is* a `ContextProvider` — and it means any future agent with a knowledge
base gets ACL and reference counting by using the provider, not by someone remembering.

## References

- [import-linter](https://import-linter.readthedocs.io/) — layers, forbidden, independence contracts
- [ADR-010](./ADR-010-per-tenant-domain-entitlement.md) — the entitlement gate `_domain_deps` carries
- [ADR-014](./ADR-014-runtime-prompt-scope-no-rebuild.md) — why `agents/helpdesk/` cannot move
- [ADR-015](./ADR-015-agentschema-replaces-the-dna-sdk.md) — what `agentdefs` inherits
- [ADR-018](./ADR-018-no-ahp-for-now.md) — the orchestration question, decided separately
