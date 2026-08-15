# ADR-019 — The Agent Framework's approval is a yes/no; LangChain's is a conversation

- **Status:** Proposed
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

**Compare properly before adopting. Do not add LangChain to the backend on the strength of
this table.**

The comparison above is real and the gap is real. It is also a gap in a feature nobody has yet
shown to be needed here: `edit`, `respond` and retry context solve problems whose frequency in
this product is **unmeasured**. The HITL spec's Phase 3 (approval metrics) is what turns that
from taste into evidence, and it is one small piece of work behind an Azure environment.

Concretely:

1. **Phase 3 first.** Emit `app.approval.decisions`, `.retries`, `.latency`, `.pending`. If
   rejections are rare and retries near zero, the gap is theoretical and this ADR closes as
   "compared, not adopted".
2. **If the data shows otherwise**, the decision is between two shapes, and it is *not*
   "rewrite on LangChain":
   - **(a)** keep the Agent Framework and accept our own failure memory for the retry context
     only — bounded, one module, no second runtime;
   - **(b)** run a LangChain/deepagents domain **alongside**, bound by a declarative document
     in the `opentag-reference` `HostBinding` shape (agent · protocol · host · policy), which
     is what ADR-018 said to do when this day came.
3. **Whichever way, the role gate stays ours.** Neither framework has a notion of a required
   role, and RULE #5 depends on it. That is not a tiebreaker; it is a constant.

## Consequences

- **+** The gap is written down with numbers, so the next person does not rediscover it by
  reading marketing pages.
- **+** ADR-018's trigger worked as designed: the condition was named in advance, it fired,
  and the response is a comparison rather than an impulse.
- **+** Option (b) has a shape already — the binding document — instead of a ports layer.
- **−** This ADR decides to measure rather than to act, which is unsatisfying when the gap is
  visible. The alternative is adopting a second runtime for a feature with no demonstrated
  demand, which is the more expensive mistake.
- **−** Phase 3 needs an Azure environment, so the evidence is gated on infrastructure that
  does not currently exist. That is a real delay, not a formality.
- **⚠** If a *product* requirement arrives that names `edit` or `respond` explicitly — "the
  approver must be able to fix the ticket summary before it is opened" — this ADR is superseded
  immediately, without waiting for metrics. Demand stated by a human beats demand inferred
  from a histogram.

## References

- `langchain/agents/middleware/human_in_the_loop.py` — `InterruptOnConfig`, `DecisionType`,
  `_DescriptionFactory` (485 lines)
- `deepagents/graph.py` — `_merge_fs_interrupt_on`, `HumanInTheLoopMiddleware` wiring
- `agent_framework.ToolApprovalMiddleware`, `agent_framework_ag_ui._approval_lifecycle`
- [ADR-018](./ADR-018-no-ahp-for-now.md) — the trigger that fired
- [ADR-009](./ADR-009-native-tool-approval-foundry-connection-resolution.md) — the earlier
  decision to use native tool approval rather than hand-rolled HITL
