# ADR-020 — Use each framework the most canonical way possible; the modular monolith is the organization

- **Status:** Accepted
- **Date:** 2026-08-15
- **Supersedes:** [ADR-018](./ADR-018-no-ahp-for-now.md) (right decision, wrong reason) and
  [ADR-019](./ADR-019-langchain-hitl-comparison.md) (framed as a runtime choice; it is not)
- **Context:** [ADR-017](./ADR-017-module-boundaries.md) (the organization this relies on),
  `2026-08-15-hitl-spec.md`, `github-copilot-agent-framework-example`, `opentag-reference`

## Context

Three decisions in one day circled the same question and got it progressively less wrong.

**ADR-018** declined an `orchestration` ports layer because *"there is no second runtime yet"*.
The decision was right and the reason was weak — it collapsed the moment a second runtime
became a **product requirement** rather than a hypothetical.

**ADR-019** compared LangChain's HITL against the Agent Framework's, found `edit` missing on
our side, and framed the answer as *"adopt LangChain"* — as if picking a winner.

**The implementation then did neither.** `edit` shipped through a small decision contract of
our own (`app/modules/hitl/`, ~130 lines) that imports no LangChain at all, on top of the Agent
Framework. It works, cost no checkpointer and no second runtime, and matched neither ADR.

That mismatch is the signal. The question was never "which runtime wins". This project is a
showcase whose product is the **assurance layer**, and an assurance layer that only works on
one runtime has not been shown to be worth anything. Several runtimes are the point:
Agent Framework, LangGraph/deepagents, Foundry hosted agents, CopilotKit on the client.

### Why an abstraction over them is the wrong instrument

Not "premature" — **wrong**, and the evidence is this repository's own timeline:

- `agent-framework` was preview; it is `1.14.0` now, and `escalation.py` still carries a
  workaround for a bug in `agent-framework-ag-ui` **1.0.0rc5**.
- **AHP** is at `v0.7.0` and its own versioning page says breaking changes are *inevitable*;
  compatibility holds only within a MINOR, and a MINOR ships every two to four weeks.
- **LangChain** has rewritten HITL more than once: `NodeInterrupt` → `interrupt_before` /
  `interrupt_after` → `interrupt()` → `HumanInTheLoopMiddleware`.
- `ToolApprovalMiddleware`, adopted here today, may not exist in six months.

A ports layer over surfaces moving that fast must be rewritten on every move. You then carry
the churn of the API **plus** the churn of the abstraction — paying twice for the privilege of
reading neither vendor's documentation nor examples, because your code no longer looks like
either.

### Both reference implementations already decided this

- `github-copilot-agent-framework-example` binds AgentSchema → `GitHubCopilotAgent` in
  **204 lines with no ports**: *"This is the whole conversion layer: data in, GitHubCopilotAgent
  out. The lifecycle — sessions, streaming, permission prompts — stays with the caller."*
- `opentag-reference` genuinely has two runtimes and **also built no ports** — it wrote one
  declarative document (`HostBinding`) and a projection function.

Neither built what the original spec asked for. That is two independent teams reaching the
same conclusion.

## Decision

**Use each framework the most canonical way its own documentation shows. Let the modular
monolith (ADR-017) be the organization. Put in `shared` only what survives a change of
runtime.**

Concretely:

1. **A module uses its framework's idioms directly.** `platform_ops` calls
   `ToolApprovalMiddleware`; a LangGraph domain would call `interrupt()` and
   `HumanInTheLoopMiddleware`; a hosted agent is packaged the way Foundry packages one. No
   wrapper whose only job is to make them look alike.
2. **The module boundary is the isolation.** `public.py` / `internal/`, enforced by
   `import-linter`. A framework's surface stays inside one module's `internal/`, so an upgrade
   is bounded by construction — which is the isolation a ports layer promised and did not need
   to provide.
3. **`shared` carries only the runtime-independent.** The test, written down so nobody has to
   guess:

   > **If I swap this domain's runtime tomorrow, is this still true?**
   > Yes → `shared`. No → the module's `internal/`.

   | Passes | Fails |
   |---|---|
   | `shared/settings` — configuration | `ToolApprovalMiddleware` — Agent Framework's |
   | `shared/auth` — caller identity and role | `WorkflowBuilder`, `interrupt()` — a runtime's |
   | `shared/telemetry` — OTEL bootstrap + the pinned `gen_ai.*` names | a checkpointer — LangGraph's |
   | `modules/hitl` — the DECISION (approve/edit/reject + required role) | the approval MECHANISM |

4. **The guarantees are contracts, not code paths.** Mandatory citation is a policy over
   output (`eval/`); the per-document ACL runs before the model, in retrieval; the Approver
   role is checked in `hitl.decide()`. None names a runtime, and that is why they hold across
   all of them.
5. **OpenTelemetry is the audit spine, and each runtime instruments it its own way.** The
   Agent Framework has `enable_instrumentation()`; LangChain has LangSmith, which speaks OTLP;
   hosted agents trace inside Foundry. `shared/telemetry` owns the **bootstrap and the names**
   — never per-runtime branching.

### The line this must not cross

**The day `shared/telemetry` grows an `if runtime == …`, the abstraction is back wearing a
different hat.** Same for any `shared` module that starts knowing which framework is calling.
`shared` may define vocabulary; it may not dispatch on runtime.

## Consequences

- **+** Vendor documentation and samples apply to our code directly, because our code looks
  like theirs. An upgrade guide is usable instead of needing translation.
- **+** A framework upgrade is bounded by a module's `internal/`, which `import-linter` already
  guards. That was the ports layer's whole promise, obtained for free from ADR-017.
- **+** The assurance layer gets proved where it matters: the same guarantees across different
  runtimes is a much stronger claim than the same guarantees on one.
- **+** It settles three ADRs into one coherent position instead of two wrong ones and an
  implementation matching neither.
- **−** **Wiring repeats.** Today ~65 lines across the `_mount_*` helpers plus 48 in
  `PerRequestAgent`; a second runtime roughly doubles it. This is accepted, not overlooked —
  and someone will eventually want to "clean it up" with exactly the abstraction this ADR
  refuses. The defence is that the reason lives in the code, not in institutional memory.
- **−** **HITL genuinely diverges.** `platform` approves with a boolean (Agent Framework); a
  LangGraph domain gets four decision types. `hitl.decide()` unifies the *decision*; the
  *mechanism* stays different, and the ApprovalCard has to render both. The design exposes the
  difference rather than hiding it — that is the intent, and it is still work.
- **−** Each runtime needs its own tests and its own upgrade watch. More surface, honestly
  more maintenance.
- **⚠** This ADR is only safe while the module boundaries hold. If `import-linter` is loosened,
  a framework's surface leaks across modules and the isolation argument collapses — at which
  point the ports layer starts looking reasonable again, for bad reasons.

## Alternatives considered

- **A ports/adapters layer over runtimes** (the original spec's `orchestration`). Uniform call
  sites, one place to swap runtimes. Rejected: it abstracts surfaces that change faster than
  the abstraction can, doubling the churn, and both reference implementations declined it.
- **Pick one runtime and standardize.** Simplest to maintain, and it destroys the point — an
  assurance layer demonstrated on a single runtime demonstrates very little, and `edit` alone
  showed no single runtime has everything.
- **A thin shim, "just for the common parts".** How every ports layer begins. The parts that
  are genuinely common are already in `shared`, and the test in Decision §3 is what keeps the
  shim from growing.

## References

- [ADR-017](./ADR-017-module-boundaries.md) — the module boundaries this relies on entirely
- [ADR-018](./ADR-018-no-ahp-for-now.md) · [ADR-019](./ADR-019-langchain-hitl-comparison.md) —
  superseded; the AHP maturity data and the HITL comparison table in them remain accurate and
  worth reading
- `github-copilot-agent-framework-example` · `opentag-reference` — two independent
  implementations that reached this conclusion first
