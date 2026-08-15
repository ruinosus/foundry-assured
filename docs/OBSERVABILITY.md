# Observability

How this backend emits telemetry, what it refuses to emit, and how to turn it on.

> **Scope.** This documents what **Phase 5.5a** shipped: the bootstrap, the pinned GenAI
> conventions, the content policy and the cost arithmetic. The HITL model (approval events,
> span links, approval metrics) and the trace↔eval link belong to **Phase 5.5b**, which has
> not shipped — see [What is not here yet](#what-is-not-here-yet). Sections describing
> unbuilt behavior are marked, not implied.

## The short version

Telemetry is **off by default**. With no exporter configured the app behaves exactly as it
did before telemetry existed — no provider, no exporter, no overhead. That is deliberate:
the whole point of adding it before the module refactor was to make regressions visible
*when someone is looking*, not to make local development depend on an Azure resource.

```
                    ┌─ APPLICATIONINSIGHTS_CONNECTION_STRING set? ─→ Azure Monitor
setup_telemetry() ──┼─ OTEL_EXPORTER_OTLP_ENDPOINT set?           ─→ OTLP over HTTP
                    └─ neither                                    ─→ no-op  (default)
```

`app/main.py` calls `setup_telemetry()` once, before anything else, so the rest of boot
happens inside it. The call is idempotent — a second call is a no-op rather than a second
provider, which would double every span.

## Why it landed before the refactor

The modular-monolith refactor (ADR-017) moved nearly every file in `apps/backend/app` under
a "no behavior change" claim. Its verification is a route snapshot plus an AG-UI fixture
comparison — both **structural**. They catch an endpoint that vanished or an event emitted
out of order. Neither can see a request that got slower, a call that started costing twice
as much, or an error rate that crept up.

So the telemetry foundation was moved ahead of the moves rather than after them, which is
also why this file exists before the HITL half does.

> **Caveat, stated rather than buried:** the performance *baseline* the phase called for —
> p50/p95 latency, cost per request, error rate, recorded before the first `git mv` — was
> **not captured**, because recording it needs a live exporter and real model calls. The
> refactor therefore ran with a structural safety net only. Capturing it is still worth
> doing, as the reference point for the next structural change.

## Turning it on

| Variable | Effect |
|---|---|
| `APPLICATIONINSIGHTS_CONNECTION_STRING` | export to Azure Monitor → Foundry *Tracing* / App Insights "Agents" view |
| `OTEL_EXPORTER_OTLP_ENDPOINT` | export to any OTLP/HTTP collector (only the HTTP exporter is installed; gRPC is deliberately not attempted) |
| `ENVIRONMENT` | becomes `deployment.environment` on the resource (default `local`) |
| `TELEMETRY_CAPTURE_CONTENT` | **off by default** — see [Content policy](#content-policy) |
| `USD_BRL` | FX rate for the BRL rollup (default `5.40`) |

Azure Monitor wins when both exporters are configured. Neither → no-op.

The connection string can also be passed directly:
`setup_telemetry(connection_string=...)`. That parameter exists for a boundary reason:
`wiki_builder` resolves the string by asking the Foundry project, which needs
`tenant_config()` — a business module. The shared kernel is not allowed to import one, and
`import-linter` enforces it, so the fallback belongs to the caller.

## What gets emitted

The `agent-framework` emits the OpenTelemetry **GenAI semantic-convention** spans itself,
once `enable_instrumentation()` runs. The expected shape:

```
invoke_agent {model}          ← one per agent run
├── chat {model}              ← one per LLM call, carries token usage
└── execute_tool {tool}       ← one per tool / MCP call
```

Useful attributes, all named from `app/shared/telemetry/conventions.py`:

- `gen_ai.request.model`, `gen_ai.response.model`
- `gen_ai.usage.input_tokens`, `gen_ai.usage.output_tokens`
- `gen_ai.response.finish_reasons`
- `gen_ai.conversation.id` — the AG-UI `thread_id`. **Never invent a fallback** (UUID,
  trace id, hash): omit it when there is none. A fabricated conversation id silently merges
  unrelated conversations in every downstream query.

Plus this repository's own: `app.domain`, `app.module`, `app.tenant_id`,
`app.deployment_mode`, `app.run.outcome`.

`app.module` mirrors the `import-linter` boundaries on purpose, so a dashboard slices the
system along the same lines CI enforces.

### Why every `gen_ai.*` string lives in one file

The GenAI semantic conventions are **pre-1.0 and still renaming things**. Every such string
comes from `conventions.py`, so a convention migration is a diff in one file instead of a
grep across the codebase.

**Never write a `gen_ai.*` literal anywhere else.** This is a red gate in the spec, and the
reason is boring but real: a renamed attribute that only got half-updated produces
dashboards that are quietly wrong rather than obviously broken.

## Content policy

Prompts, model messages, tool arguments and retrieved documents are **not** emitted unless
someone sets `TELEMETRY_CAPTURE_CONTENT=true`. When switched on, content goes into span
**events** with redaction — never into span **attributes**, which are indexed, retained and
hard to purge.

Two rules hold regardless of the switch (invariant I-10):

1. **ACL-trimmed documents never enter telemetry with their content.** The per-document ACL
   (Rule #6) exists so a caller sees only what they are entitled to. A trace is read by
   operators the ACL never checked, so putting retrieved content there would route around
   the control.
2. **Approver identity stays out.** The HITL model records the approver's *role*. The person
   belongs in the application's audit log, which has its own access rules.

Redaction is a backstop, not the control — the control is that capture is off. It strips
AWS keys, JWTs, `Bearer` tokens and `key=value` secret assignments, and caps values at 2000
characters.

## Cost

`app/shared/telemetry/cost.py` turns token usage into money — the number dashboards do not
compute. Tokens are measured exactly, from the same gen_ai usage the framework emits.
**Prices are editable estimates**; confirm them against actual billing before trusting a
total.

```python
from app.shared.telemetry.cost import CostMeter

meter = CostMeter("gpt-5-mini")
meter.add(response)     # one agent response at a time
print(meter.report())   # tokens in/out, USD, BRL, and the prices used
```

`price_for()` resolves **longest prefix first**. That is not cosmetic: the original version
iterated the dict in insertion order, so `gpt-5-mini` got the right price only because that
key happened to be written above `gpt-5`. Reordering the literal would have priced it 5×
too high, silently.

The module is pure arithmetic — no OTEL import, no I/O, no global state — so it stays
testable offline. Emitting the resulting metric is the caller's job.

## Verifying it

```bash
# from apps/backend/
uv run python -m tests.shared.telemetry_test
```

Asserts the two things most likely to go wrong: that the default really is a no-op, and that
content capture really is opt-in. Also covers redaction, the convention names and the cost
arithmetic. It runs in CI on every push.

To see the traces end to end you need a live exporter and real model calls — set
`APPLICATIONINSIGHTS_CONNECTION_STRING`, run the app, and open the Foundry *Tracing* view.

## What is not here yet

Phase 5.5b, which depends on Phase 3.5:

- **Approval as first-class telemetry.** A span is *never* held open across a human wait.
  The request emits `approval.requested` and the run's span closes with
  `app.run.outcome = "interrupted_for_approval"`; the resume is a **new trace with a span
  link** back to it. The attribute names are already pinned in `conventions.py` so the two
  phases cannot disagree about them — but nothing emits them yet.
- **Approval metrics** — `app.approval.latency` (requested→decided), `.pending`,
  `.decisions` (granted/rejected/expired), `.retries`. A high rejection rate is a *quality*
  signal: the agent is proposing bad actions.
- **Deeper instrumentation** — the workflow executors, the grounded pipeline (which needs
  explicit OTEL context propagation through the streaming generator, since the contextvar is
  already lost there), per-MCP-call `execute_tool`, and `guardrail.decline` when the agent
  refuses an off-corpus question.
- **The trace↔eval link** — every eval record carrying `trace_id` + `gen_ai.conversation.id`,
  so a production failure becomes a case in the golden set.
- **The performance baseline** described above.

## References

- [ADR-017](./adr/ADR-017-module-boundaries.md) — the module boundaries `app.module` mirrors
- `apps/backend/app/shared/telemetry/` — the implementation
- `apps/backend/tests/shared/telemetry_test.py` — the guard
