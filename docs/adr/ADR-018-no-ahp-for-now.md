# ADR-018 — No orchestration abstraction, and not AHP either — the registry is already the thin shell

- **Status:** Accepted
- **Date:** 2026-08-15
- **Context:** [`apps/backend/app/domains.py`](../../apps/backend/app/domains.py),
  [`apps/backend/app/agents/per_request.py`](../../apps/backend/app/agents/per_request.py),
  [`apps/backend/app/workflow/escalation.py`](../../apps/backend/app/workflow/escalation.py),
  [`apps/backend/app/agents/mcp/registry.py`](../../apps/backend/app/agents/mcp/registry.py),
  the consolidated spec `2026-08-15-modular-monolith-consolidated-spec.md` §2.5
- **Related:** [ADR-017](./ADR-017-module-boundaries.md) — the module list this ADR keeps
  `orchestration` out of

## Context

This backend runs four agent shapes with no common abstraction: a `WorkflowBuilder` graph
(helpdesk, with structural HITL through `ctx.request_info()`), a hand-rolled four-station
grounded pipeline (cockpit, selfwiki), a single tool-driven agent with per-request MCP brokering
(platform), and a Responses→AG-UI bridge (hosted). The consolidated spec's first revision read
that as missing abstraction and proposed an `orchestration` module: `AgentBlueprint`,
`OrchestrationRuntime` (Protocol), `ApprovalContract`, `ToolCatalog` + `PolicyFilter`,
`IdentityContext` — plus a LangGraph adapter delivered as a stub raising `NotImplementedError`.

Two things then happened. Microsoft shipped the **Agent Host Protocol (AHP)**, and this
repository's own history — ADRs 008, 009, 011, 012, 015 — kept teaching the same lesson: do not
hand-roll what the vendor already ships. The question is whether AHP is that vendor primitive
for orchestration, and whether the `orchestration` module should be built at all.

### What AHP actually is, measured

AHP is a **client ↔ host** protocol: JSON-RPC, an immutable Redux-like state tree mutated by
ordered actions through pure reducers, with write-ahead reconciliation so several clients
converge on one synchronized view of an agent session. Channels are URI-addressed —
`ahp-session:/<uuid>`, `ahp-chat:/<uuid>`, plus terminal, mcp, comments, resource-watch and
telemetry.

It standardizes two things this repository has hand-built:

- **Sessions**, host-authoritative: turns, forks, side chats, synchronized drafts, cursor-paged
  history, replay, reconnect/resume.
- **Confirmations**: a tool call enters `pending-confirmation`; any subscribed client dispatches
  `chat/toolCallConfirmed`; the first wins and later ones are rejected. Separately, *elicitation*
  (`chat/inputRequested` → `chat/inputAnswerChanged` → `chat/inputCompleted`) records a durable
  `InputRequestResponsePart` in the turn with typed questions and an `accept | decline | cancel`
  outcome. Approval as durable transcript state is genuinely better for audit than the ephemeral
  interrupt used here today.

And its doctrine lists as explicit **anti-goals**: *"how agents reason, plan, call tools, or
manage context"*, *"a required model provider, model router, or credential flow"*, *"a universal
backend tool registry or tool schema"*, and *"a replacement for ACP or other downstream agent
protocols"*. The layering is stated plainly: AHP sits **above** the host; prompts, streaming,
tool execution and permissions sit **below** it.

**Maturity, measured, not inferred:** repository created 2026-03-12; latest release **v0.7.0**
on 2026-07-31; MINOR releases on 2026-06-06, 06-19, 06-26, 07-20, 07-31. Its own versioning page
says *"Unlike LSP or DAP — which largely guarantee backwards compatibility in perpetuity — the
design space for agent hosts is open-ended and moving quickly. **Backwards-incompatible changes
to AHP are inevitable.**"*, and pre-1.0 compatibility holds **only within the same MINOR**. A
new MINOR every two to four weeks is, by the protocol's own rule, a compatibility break.

### What the two reference implementations actually do

- `github-copilot-agent-framework-example` binds an AgentSchema `PromptAgent` to
  `GitHubCopilotAgent` in **204 lines with no ports at all** — *"This is the whole conversion
  layer: data in, GitHubCopilotAgent out. The lifecycle — sessions, streaming, permission
  prompts — stays with the caller."* It exposes it over **AG-UI**, not AHP; its own
  `scope.yaml` says so, and the repository contains zero AHP references.
- `opentag-reference` does have two runtimes, and **also built no ports**. It wrote a
  declarative document: a `HostBinding` naming agent, `protocol: ahp`, a portable host
  reference and `policy: {sessions, reconnect, confirmations}`, with a projection function that
  refuses unsupported policies at load. Its AHP client is TypeScript in the browser; the Python
  agent never speaks AHP, and the host is **VS Code Agent Host**, an external process the
  deployment starts.

## Decision

**Do not build the `orchestration` module, and do not adopt AHP now. Keep `registry.py`'s
dispatch-by-`kind` as the thin shell it already is, and spend the effort on declaration instead
— moving approval policy and per-tool role gates into the AgentSchema documents.**

### Why AHP is not the missing abstraction

Mapping the five proposed ports against what AHP defines:

| Proposed port | Covered by AHP? |
|---|---|
| `AgentBlueprint` (archetype, runtime, instructions, tool/approval/memory policy) | **No** — "how agents reason, plan, call tools, or manage context" is a stated anti-goal |
| `OrchestrationRuntime.build() → AGUIServable` | **No** — agent construction sits *below* the host; AHP is the layer above |
| `ToolCatalog` + `PolicyFilter` | **No** — "a universal backend tool registry or tool schema" is a stated anti-goal |
| `IdentityContext` (OBO credential, roles, tenant) | **No** — "a required credential flow" is a stated anti-goal |
| `ApprovalContract` | **Partly** — `chat/toolCallConfirmed` and elicitation cover the interaction; neither `required_role` nor `attempt`/`previous_error` is covered |

One of five, partly. AHP is not a substitute for the module — by design.

Adopting it here would also mean one of two things, and neither is "use the vendor's plumbing":
running VS Code Agent Host as our sessions server, which is nonsense for a multi-tenant SaaS
with Entra OBO and per-document ACL; or **writing an AHP host** — root/session/chat channels,
reducers, subscriptions, replay, reconnect, write-ahead reconciliation — against a 0.x protocol
that breaks every MINOR, to serve a browser client already served by AG-UI + CopilotKit.

The house lesson is not "adopt the Microsoft protocol". It is **do not re-implement what
Microsoft shipped *and stabilized***. AHP is shipped and explicitly not stabilized.

### Why the module should not be built anyway

Its concrete deliverables were: move `PerRequestAgent` — **48 lines, ~24 of real code** — and
the mount dispatch (~65 lines) behind five ports, and add a LangGraph adapter that raises
`NotImplementedError`. The stub is the diagnosis: the abstraction's reason to exist is a second
runtime that is not in the repository, and the spec's own Phase 8 said to implement it "when a
LangGraph domain actually enters the monolith". Five ports for a hypothetical consumer is
premature abstraction — the mirror image of the mistake, not its opposite.

Both reference implementations agree empirically: neither built ports, and the one with two
runtimes reached for **one more declarative document**.

### What is done instead

`app/agents/mcp/registry.py` carries 175 lines of Python with `min_role`/`min_role_write` per
tool — access policy **as code**, where CLAUDE.md Rule #6 says access control is **data**. The
Copilot example shows the shape: derive the gated set from the document, reading the standard
`approvalMode` on `McpTool` and a **namespaced** extension for what the schema does not model
(function tools have no approval field). The substrate is already here — prompts are AgentSchema
documents with a `x-foundry-assured` metadata bag, publishable without a rebuild (ADR-014).

So the policy moves into the documents, gated by a parity test proving the resulting
`(tool, min_role, requires_approval)` set is identical to today's. The mechanism does not move.

### What stays ours regardless

The four assurance guarantees all fall inside AHP's anti-goals. That is good news twice: no
protocol will take them away, and no protocol will enforce them for us.

| Guarantee | Why no protocol can own it |
|---|---|
| Mandatory citation in the resolver (Rule #4) | a policy over model output; AHP has no groundedness concept. Lives in `eval/`. |
| Per-document ACL (Rule #6) | AHP anti-goal, and structurally impossible to delegate: the trim happens **before** the model, and a client-facing protocol acts after. |
| Approver role gate on HITL (Rule #5) | AHP standardizes the *interaction* and explicitly leaves authorization out — *"any client can resolve it"*. `escalation.py`'s `has_role("Approver","Admin")` would still be ours under AHP, word for word. |
| Wiki build-fidelity gate | outside AHP, AgentSchema and AG-UI alike. It is the product. |

### Re-evaluation trigger

This decision is revisited when **any** of these is true:

1. AHP reaches **1.0** (its own versioning page makes pre-1.0 breakage a stated expectation).
2. A **second runtime** actually lands in the monolith — at which point start from a declarative
   binding document in the `opentag-reference` shape, not from Python ports.
3. A **second client surface** needs to attach to a live session — ops handoff, Teams/Slack,
   two operators on one incident. The `platform` domain is the natural first candidate: a
   tool-driven ops concierge with human-approved writes is precisely AHP's use case, and
   confirmation-as-durable-state would be a real audit gain over today's interrupt.

Until then: no ports, no adapters, no stubs for runtimes that are not in the repository.

## Alternatives considered

- **Build the `orchestration` module as specified.** Delivers the seam before the second runtime
  arrives, so the second one is cheap. It also freezes today's four shapes into port signatures
  designed with zero information about what the second runtime needs — the stub is proof that
  the information is missing. Rejected.
- **Adopt AHP now, write our own host.** Gets multi-client sessions, replay and durable
  confirmations, and standardizes the surface we would otherwise hand-roll. Costs an entire host
  implementation against a protocol that breaks every MINOR, for capabilities no user has asked
  for. Rejected on timing, not on merit.
- **Adopt AHP with VS Code Agent Host as the host.** The reference arrangement, and the only one
  with a shipping implementation. Incompatible with per-tenant Entra OBO, entitlement gating and
  per-document ACL. Rejected.
- **Keep everything in Python and skip the declarative move too.** Zero work now; leaves access
  policy as code in violation of Rule #6, and leaves the one thing the reference implementations
  agree on unused. Rejected — this is the part with an actual payoff.
- **Wait for AHP 1.0 before deciding anything.** Defers a decision that blocks Phase 3.5.
  Rejected in favor of deciding now with an explicit trigger, which is the same thing minus the
  blocking.

## Consequences

- **+** No new abstraction layer to design, review, maintain or explain, and no stub pretending
  to be an extension point.
- **+** The effort lands where Rule #6 already pointed: per-tool access policy stops being
  Python. `mcp/registry.py` loses its policy half.
- **+** The decision is written down with a measurable trigger, so revisiting it is a fact check
  rather than a re-argument.
- **+** Everything AHP does define — session sync, replay, durable confirmations — remains
  available later precisely because nothing here was built to compete with it.
- **−** If a second runtime arrives sooner than expected, its integration starts from four
  concrete shapes instead of a ready seam. Accepted: the binding-document path is the cheaper
  starting point, and it will be designed with real information.
- **−** The four agent shapes stay visibly different. Anyone reading `registry.py` still meets
  three `_mount_*` functions. That is 65 lines of honest duplication, not a design flaw.
- **⚠** AHP moves fast. A note in this ADR is not monitoring; if trigger (1) matters, someone has
  to check the releases.

## References

- [Agent Host Protocol](https://github.com/microsoft/agent-host-protocol) ·
  [doctrine](https://github.com/microsoft/agent-host-protocol/blob/main/docs/guide/doctrine.md) ·
  [versioning](https://github.com/microsoft/agent-host-protocol/blob/main/docs/specification/versioning.md) ·
  [chat channel](https://github.com/microsoft/agent-host-protocol/blob/main/docs/specification/chat-channel.md) ·
  [elicitation](https://github.com/microsoft/agent-host-protocol/blob/main/docs/guide/elicitation.md)
- [AHP and the Agent Client Protocol](https://microsoft.github.io/agent-host-protocol/guide/ahp-and-acp) — the layering
- [ADR-009](./ADR-009-native-tool-approval-foundry-connection-resolution.md) — the same lesson, applied to HITL
- [ADR-015](./ADR-015-agentschema-replaces-the-dna-sdk.md) — the same lesson, applied to agent definitions
- [ADR-017](./ADR-017-module-boundaries.md) — the module list that excludes `orchestration`
