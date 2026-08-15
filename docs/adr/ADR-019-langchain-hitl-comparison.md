# ADR-019 — The Agent Framework's approval is a yes/no; LangChain's is a conversation

- **Superseded by:** [ADR-020](./ADR-020-canonical-frameworks-modular-organization.md) — the decision was framed as a runtime choice; it is not. The HITL comparison table remains accurate.
- **Status:** **Accepted — adopt `edit`.** Superseded its own "measure first" stance within hours, by the escape hatch it wrote (see Decision)
- **Date:** 2026-08-15
- **Amends:** [ADR-018](./ADR-018-no-ahp-for-now.md) — its re-evaluation trigger fired
- **Context:** [`2026-08-15-hitl-spec.md`](../../2026-08-15-hitl-spec.md),
  [`apps/backend/app/modules/platform_ops/internal/platform.py`](../../apps/backend/app/modules/platform_ops/internal/platform.py),
  `opentag-reference` (deepagents 0.6.12 / langchain), `agent-framework 1.14.0`

## Context

ADR-018 declined AHP and declined building an orchestration ports layer, and named the
condition that would reopen it: *"a second runtime actually landing in the monolith … start
from a declarative binding document, not from ports."*

That condition has now been raised deliberately, by the repository owner, for a concrete
reason: the HITL spec's Phase 2 died on a limitation. The Agent Framework does not give the
client enough to show an approver *why they are being asked again*. The question became
whether LangChain does — and it does, by a wider margin than expected.

### Measured, against the installed packages

Not from documentation. `agent-framework 1.14.0` in this repo; `langchain` +
`deepagents 0.6.12` in `opentag-reference`'s virtualenv.

| | Agent Framework (Python) | LangChain `HumanInTheLoopMiddleware` |
|---|---|---|
| Decisions available | **approve / reject** (a boolean) | **`approve` · `edit` · `reject` · `respond`** |
| Rejection carries a reason | no — a fixed string, `"Error: Tool call invocation was rejected by user."` | `RejectDecision.message` — *"the message sent to the model explaining why"* |
| Human can fix the arguments | **no** | `EditDecision` — an edited action the agent then performs |
| Human can answer instead of executing | **no** | `RespondDecision.message` — a synthetic `ToolMessage` to the model |
| Prompt text | static (tool name + arguments) | `description: str \| _DescriptionFactory`, where the factory is `(tool_call, state, runtime) -> str` |
| Per-tool policy | `approval_mode` on the tool | `interrupt_on: dict[str, bool \| InterruptOnConfig]` |
| Auto-approval hook | `auto_approval_rules: Sequence[Callable[[Content], bool]]` | `_should_interrupt` on the middleware |
| Standing approvals / queueing | `ToolApprovalMiddleware` (queue 16, standing 1) | — |
| Required role | **neither** — ours, in both worlds | **neither** |

Source counts that settle the Phase 2 question: `_approval_lifecycle` (1026 lines) has
`metadata` 0, `attempt` 0. `ToolApprovalMiddleware` (286 lines) has `attempt` 0, `fail` 0,
`previous` 0 — it remembers **approvals**, not **failures**.

### The difference that matters

The `_DescriptionFactory` receives the agent **state**. That is the hook the Agent Framework
lacks: with the state in hand, "attempt 2, the previous one failed with X" is *derived*, not
tracked in a parallel structure. Without it, the same feature requires us to keep our own
failure memory — which is exactly the `ApprovalContract` the HITL spec exists in order not to
build.

So the Phase 2 conclusion ("the data does not exist") was right for our stack and wrong as a
general statement. The data is derivable; our framework does not expose the derivation point.

### What the reference implementation actually does

Worth recording, because it cuts against a naive reading: `opentag-reference` has
`interrupt_on` available and **does not use it**. It hand-rolls approval in
`write_confirmation.py` (273 lines) with `copilotkit_interrupt`, an `OrderedDict` capped at 64
entries, and a `(thread, tool)` failure key. Having the richer mechanism did not stop them
from building the poorer one.

Two readings, both worth holding: the richer mechanism may be harder to reach than it looks
from the type signatures — or that code predates it. Either way, "LangChain has `edit`" is not
the same as "using `edit` is easy", and this ADR should not be read as claiming it is.

## Decision

**Adopt LangChain's HITL for the approval surface, because `edit` is a stated product
requirement.**

This ADR was written recommending "measure before adopting", with one escape hatch:

> *"If a **product** requirement arrives that names `edit` or `respond` explicitly … this ADR
> is superseded immediately, without waiting for metrics. Demand stated by a human beats
> demand inferred from a histogram."*

That requirement arrived. The approver must be able to **correct the action before approving
it** — not only accept or refuse it. The Agent Framework offers a boolean; no amount of
metrics changes that.

The metrics (HITL spec Phase 3) remain worth building, but their purpose changes: they are no
longer the gate on this decision, they are the audit record of it.

### Observability and audit — already compatible, by accident of an earlier choice

The concern that made this decision hard was auditability: adding a second runtime usually
means a second observability stack, and an audit trail split across two systems is not an
audit trail. Measured, it is not the case here.

- **LangSmith exposes an OTLP endpoint** — `https://api.smith.langchain.com/otel`, driven by
  the standard `OTEL_EXPORTER_OTLP_ENDPOINT` and `OTEL_EXPORTER_OTLP_HEADERS`. It is the
  default backend for LangChain 1.0 / LangGraph 1.0, and it is **not** a proprietary protocol.
- **Azure Monitor also ingests OTLP.**
- **`shared/telemetry` already speaks OTLP.** `setup_telemetry()` (Phase 5.5a) wires
  `OTLPSpanExporter()` when `OTEL_EXPORTER_OTLP_ENDPOINT` is set, and that exporter reads
  `OTEL_EXPORTER_OTLP_HEADERS` from the environment on its own — verified in the installed
  package. Pointing this backend at LangSmith is **configuration, not code**.

So OpenTelemetry is the common denominator, and we are already standing on it. Both runtimes
can emit into the same trace store, which is what makes one audit trail possible. That was not
foresight — Phase 5.5a chose OTLP because it was the vendor-neutral option — but it is the
reason this decision is affordable.

### What LangChain itself recommends

`interrupt()` is the modern standard, superseding `NodeInterrupt` and the older
`interrupt_before` / `interrupt_after`. For tool-call approval specifically,
`HumanInTheLoopMiddleware` with `interrupt_on` is the layer that carries the four decision
types — it is built on the same interrupt machinery, not an alternative to it. Both require a
**checkpointer**: the interrupt persists graph state and resumes with `Command(resume=…)`.

That checkpointer is a real new dependency, and the honest cost of this decision.

### Shape of the adoption

Per ADR-018, which named this exact situation: **start from a declarative binding document**,
not from a ports layer. The `opentag-reference` `HostBinding` shape (agent · protocol · host ·
policy) is the reference, and `opentag-reference` is also the proof that a LangGraph agent and
this stack can coexist.

Non-negotiable regardless of runtime: **the role gate stays ours.** Neither framework has a
notion of a required role, and RULE #5 depends on it.

## Consequences

- **+** The approver gets `edit`, which no amount of work on the Agent Framework side would
  have produced. The product requirement is met rather than negotiated down.
- **+** **One audit trail, not two.** Both runtimes emit OpenTelemetry; LangSmith and Azure
  Monitor both ingest OTLP; `shared/telemetry` already speaks it. This is the single fact that
  makes a second runtime affordable, and it exists because Phase 5.5a chose the vendor-neutral
  option rather than the convenient one.
- **+** The adoption has a shape already (`HostBinding`) and a working reference
  (`opentag-reference`), instead of a ports layer designed in the dark.
- **−** **A checkpointer is a new dependency.** LangGraph interrupts persist graph state; that
  store has to exist, be operated, and be reasoned about for tenancy. It is the honest price
  of this decision and it is not small.
- **−** **Two agent runtimes in one backend.** More surface, more upgrades, more ways for the
  two HITL paths to drift apart. ADR-018's argument against premature ports still holds — what
  changed is that the second runtime stopped being hypothetical.
- **−** The `platform` domain just adopted `ToolApprovalMiddleware` (HITL spec Phase 1, already
  merged). That work is not wasted — it is the right thing for a domain staying on the Agent
  Framework — but the two domains will now approve through different machinery, and the
  ApprovalCard has to render both.
- **✅ The spike ran, and `edit` round-trips.** The warning below was answered before
  committing, not after. `tests/hitl/edit_roundtrip_test.py` drives the real middleware with
  no model: the agent proposes `{"summary": "pod crashloop", "priority": "low"}`, the human
  answers with an `EditDecision` carrying corrections, and the tool executes with
  `{"summary": "Kubernetes pod in CrashLoopBackOff", "priority": "high"}` — the human's
  values, not the model's. Nothing executes while the interrupt is pending. It stayed as a
  test rather than a scratch file, because if it goes red the decision behind this ADR is void.

  Two things the source showed that no article did: `edit` replaces `name` and `args` while
  **keeping the tool-call `id`**, and `reject` carries a message whose default explicitly tells
  the model *not to retry*. Also worth recording for whoever writes the tests: the
  `langchain_core` fakes do not implement `bind_tools` and the agent factory calls it
  unconditionally, so testing this offline needs a small model double.

## References

- `langchain/agents/middleware/human_in_the_loop.py` — `InterruptOnConfig`, `DecisionType`,
  `_DescriptionFactory` (485 lines)
- `deepagents/graph.py` — `_merge_fs_interrupt_on`, `HumanInTheLoopMiddleware` wiring
- `agent_framework.ToolApprovalMiddleware`, `agent_framework_ag_ui._approval_lifecycle`
- [ADR-018](./ADR-018-no-ahp-for-now.md) — the trigger that fired
- [ADR-009](./ADR-009-native-tool-approval-foundry-connection-resolution.md) — the earlier
  decision to use native tool approval rather than hand-rolled HITL
