# ADR-025 — The citation *vocabulary* is the framework's; the citation *transport* stays ours until upstream closes the gap

*Proposed.*

## Context

The evidence panel — the shipped surface that shows where each claim came from — is fed by an
AG-UI `CustomEvent(name="sources")` emitted by the hand-written grounded stream
(`grounded/internal/grounded.py`). That hand-written loop is the last place in the backend where
a runtime talks to the model through our own code rather than the framework's, and the standing
rule is that hand-written code survives only where a gate proves the platform does not cover it.

Three questions were measured, not assumed.

**Is there a canonical citation type?** Yes — in *both* frameworks, and we had been ignoring both:

| | shape |
|---|---|
| `agent_framework.Annotation` | `type="citation"` · `title` · `url` · `snippet` · `annotated_regions` |
| `langchain_core.messages.Citation` | `type` · `id` · `url` · `title` · `start_index` · `end_index` · `cited_text` |

Our `{index, source, url, content}` was the same data under invented names. That half is already
fixed (PR #169): the emitted shape is now the framework's, so the day transport becomes native the
payload needs no translation.

**Does the protocol carry citations?** No. AG-UI defines 38 event types and none is a citation or
source event. `CustomEvent` is the protocol's own sanctioned carrier for payloads outside the
standard set, so using it is the designed path, not a workaround.

**Does the adapter carry them?** No — and this is the whole remaining gap. Measured, reproducibly:

```python
Content("text",  annotations=[{"type": "citation", ...}])  →  [TextMessageStart, TextMessageContent]
Content("usage", usage_details={...})                      →  [CustomEvent]
```

`_emit_text` in `agent_framework_ag_ui/_run_common.py` reads only `content.text`. Four lines below
it, `_emit_usage` does exactly the thing that is missing — `CustomEvent(name="usage", value=...)`.
Same file, same dispatcher: one content type gets a custom event, its neighbour does not.

Two facts make this a gap rather than a design choice. Upstream issue
[#7460](https://github.com/microsoft/agent-framework/issues/7460) ("Python: Citation Annotation
Support for Responses API and AGUI") is **open**, labelled `ag-ui`, and assigned — with no PR and
no cross-references since 2026-08-03. And issue #3752 ("[AG-UI] Usage and Annotations are not
present") is **closed** with usage fixed and annotations not: the pattern was accepted once
already, on the same pair of concerns.

Note one thing the upstream issue does *not* cover, and that matters for anyone reading it as our
case: it describes annotations being lost in **parsing** (SharePoint grounding, `AnnotationURLCitation`
logged as "Unparsed"). Measured against the installed `agent_framework_openai` 1.8.2, parsing works
for Azure AI Search citations — the package even enriches them with per-document REST URLs. We are
unaffected by the parsing half because we produce the annotations ourselves from our own `retrieve()`.
Only the emission half applies to us.

## Decision

**Keep the hand-written grounded stream**, and keep the `CustomEvent` transport, until the adapter
emits annotations.

**There IS a public route, and it was found by looking again — so do not monkeypatch.**

The adapter's **workflow** runtime has a generic branch its own comment labels *"custom workflow
events"*:

```python
yield CustomEvent(name=_event_name(event), value=_custom_event_value(event))
```

`_event_name` returns `event.type`, and `WorkflowEventType` is a `Literal` — a type hint with no
runtime effect. So `ctx.add_event(WorkflowEvent("sources", data=[...]))` from a workflow executor
reaches the frontend as `CustomEvent(name="sources")`, through published API only:
`WorkflowContext.add_event` and `WorkflowEvent` are both public. Verified end to end, and the branch
order checked by reading — `sources` matches none of `superstep_*`, `executor_*`, `request_info`,
`output`/`data`, `status`, so it falls through.

The loose thread, said rather than hidden: `"sources"` is outside the `Literal`, so a type checker
complains. That is a typing complaint, not a runtime one, and the generic branch exists for exactly
this — but it is slack, not a guarantee, and `tests/helpdesk/sources_event_test.py` watches the two
facts it rests on.

This route already paid for itself: **the helpdesk gained the evidence panel it never had.** It is
already a workflow, so the cost was one small executor; before it, the panel fell back to a regex
guessing filenames out of the answer text.

It also changes what converting the two grounded domains would cost. They were kept hand-written
because a plain framework *agent* cannot emit the event; as *workflows* they can, with public API.
That conversion is not taken here — it still rewrites the most delicate path in the system (OBO,
ACL, citations) — but the reason for not doing it is now **cost, not impossibility**.

The routes rejected:

- *Monkeypatch `_emit_text` / `_emit_content`* — private, module-level, hard-coded dispatch. Our own
  code breaks when *we* change it; a monkeypatch breaks when *they* ship a minor (ADR-020). With a
  public route available this one has no argument left at all.
- *Wrap the event stream* — also reaches non-public surface (`run_agent_stream`).

*Contributing upstream* stays the right permanent fix, and is a separate decision with its own cost
(their CONTRIBUTING asks for a test with every fix and discussion before large changes). This ADR
does not commit to opening it; it records that the option is good and the evidence is ready.

## Consequences

- **+** The remaining hand-written code has exactly **one** named cause with an issue number, not a
  vague "it's custom". The re-evaluation trigger is mechanical: when #7460 closes, `techdocs` and
  `selfwiki` become plain framework agents, the SSE loop is deleted, and the payload already matches.
- **+** The vocabulary alignment (PR #169) already banked most of the value: whoever migrates later
  translates nothing.
- **−** Two domains keep a hand-written stream, which means they keep their own recording calls
  rather than inheriting the framework seams. They satisfy the standing rule — one recording point
  per runtime — but by their own code rather than by construction.
- **−** The gap depends on a third party's queue. Nothing in our CI can make #7460 close.
- **⚠** If the adapter starts emitting annotations under a *different* event name than ours, the
  frontend needs to accept both for one release, exactly as it now accepts the pre-#169 shape.

### The re-evaluation trigger

Revisit when **[microsoft/agent-framework#7460](https://github.com/microsoft/agent-framework/issues/7460)
closes**, or when `agent_framework_ag_ui` emits a citation event under any name — whichever comes
first. Check by running the three-line reproduction in the Context section against the installed
package; it is the whole test.

## References

- [microsoft/agent-framework#7460](https://github.com/microsoft/agent-framework/issues/7460) — open, `ag-ui`, assigned, no PR
- microsoft/agent-framework#3752 — closed; usage fixed, annotations not (the precedent)
- [AG-UI protocol](https://docs.ag-ui.com/introduction) — 38 events, none for citations
- [ADR-020](./ADR-020-canonical-frameworks-modular-organization.md) — why we do not abstract over volatile surfaces
- `tests/grounded/citation_vocabulary_test.py` — the gate that keeps both sides on the canonical shape
- `tests/helpdesk/sources_event_test.py` — the gate that keeps the public route from being lost by accident
- [AI SDK stream protocol](https://ai-sdk.dev/docs/ai-sdk-ui/stream-protocol) — the neighbouring
  protocol treats sources as first-class (`source-url`, `source-document`, plus a `<Sources>`
  component). AG-UI has no citation event and, searched, **no issue asking for one** — the gap is
  not a decision against it; nobody has raised it
