# Backend state and persistence

This repository does not hide runtime state behind one generic persistence layer. Different domains own different state because they have different correctness and lifecycle requirements. This page is the canonical map of those owners, with the conversations subsystem expanded because this range changed how evidence is persisted and replayed. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/public.py#L5-L25)

This page is paired with Grounded Domains for runtime emission of citations and with the frontend Assurance Console for how persisted evidence is replayed in the UI.

## Tenant control-plane state

`TenantRecord` remains the main persisted control-plane document. It includes tenant identity, lifecycle status, data-plane config, `Connection` references, and enabled domains. It is stored either in-memory for tests and dev or in Azure Table Storage for shared mode. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/tenancy/internal/tenant_store.py#L15-L37) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/tenancy/internal/tenant_store.py#L85-L99) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/tenancy/internal/tenant_store.py#L111-L145)

This state still matters before any domain runtime runs: shared mode cannot resolve tenant-specific services without it.

## Per-user memory state

Helpdesk memory still uses `FoundryMemoryProvider`, configured by tenant data-plane settings and scoped with `memory_scope()`. The provider both reads previous facts and stores new ones; it is not a simple cache. Scope isolation remains `tid:oid` in shared mode and `oid` otherwise. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/helpdesk/internal/memory.py#L1-L10) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/helpdesk/internal/memory.py#L27-L40) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/tenancy/internal/tenant_resolution.py#L71-L82)

## Conversation history and evidence state

The most important persistence change in this range is that conversation history now stores response evidence with the assistant message itself. `record_turn(...)` accepts `citations`, and when citations exist it writes them into the assistant message as `annotations`. That keeps the evidence attached to the specific response that produced it instead of leaving it as a live-only side channel. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/listing.py#L84-L127) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/conversations/citations_persisted_test.py#L40-L67)

That change matters because the frontend now rehydrates evidence from stored messages. If `annotations` are missing, reopening a conversation loses source attribution even though the original response was cited. The persistence contract is therefore: **evidence belongs to a message, not to the session as a whole**. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/conversations/citations_persisted_test.py#L1-L10) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/conversations/citations_persisted_test.py#L84-L98)

### Storage format and ownership

Conversation storage still lives in `app/modules/conversations/internal/store.py`. The durable shape is append-only JSONL keyed by user, agent, and conversation id, while the in-memory fake preserves the same API for tests and CI. `ConversationMeta` now remains the minimal list-side summary, while the message bodies carry the full evidence payload. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/store.py#L54-L70) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/store.py#L76-L120)

The practical ownership split is:

- `store.py` owns durable shape, sanitization, and listing-friendly metadata; [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/store.py#L219-L260)
- `listing.py` owns read and write orchestration such as `record_turn`, `record_usage`, and hybrid listing with service-side Foundry sessions; [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/listing.py#L31-L43) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/listing.py#L139-L170)
- `provider.py` owns the framework-facing history provider that loads and saves full conversation messages for agent runtimes. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/provider.py#L1-L27)

### Sanitization boundary

`sanitize(...)` is still the single write-time redaction point, and it now explicitly walks citation annotations too. Both flat `annotations[]` and nested `contents[].annotations[]` are redacted, including untyped nested fields such as `additional_properties` and `raw_representation`. The goal is to preserve citation labels and indices while ensuring snippets do not bypass the ADR-023 redaction boundary. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/store.py#L162-L216) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/store.py#L219-L260) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/conversations/citations_persisted_test.py#L69-L125)

When changing evidence payload shape, this is the first file to inspect. A new citation field is not complete until `sanitize(...)` either preserves it intentionally or redacts it intentionally.

### Duplicate-response collapse

The published-agent path introduced a second persistence hazard: the service can produce both an accumulated local assistant reconstruction and a final assistant message for the same turn. `provider.py` now collapses those duplicate assistant reconstructions before persistence so one turn does not become two assistant messages. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/provider.py#L88-L142) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/conversations/duplicate_response_test.py#L52-L83) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/tests/conversations/duplicate_response_test.py#L85-L130)

That invariant matters for both UX and accounting: duplicate assistant writes would create duplicated replayed responses and misleading usage/conversation counts.

## Usage accounting state

Usage accounting remains attached to the current conversation through `bind_dependency(...)`, `current_conversation()`, and middleware hooks in `recorder.py`. The important recent distinction is that published-agent paths need `AgentUsageRecorder`, not just `ChatMiddleware`, because `FoundryAgent.middleware` is agent-level and would ignore chat middleware silently. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/recorder.py#L47-L90) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/internal/recorder.py#L114-L186)

The resulting rule is simple but easy to violate: **usage recording only works when the runtime binds a conversation before model calls begin**. If you add a new route family or runtime and forget `bind_dependency(...)`, token accounting quietly disappears. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/conversations/public.py#L14-L24)

## Ticket persistence

Tickets remain persistent domain outcomes rather than transient events. The `/tickets` API surfaces the real tickets opened by approval flows, and deployed environments still place them on Azure Files-backed storage so they survive scale-to-zero. Oncall escalation continues to write through `create_ticket`, so helpdesk and oncall share this durable sink. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/tickets/api.py#L9-L15) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/oncall/internal/graph.py#L78-L85)

## Hosted client cache

Hosted-agent bridging still uses a process-global `_clients` cache keyed by hosted agent name. Each entry stores an async OpenAI client, project client, and credential. `aclose()` remains the release valve, and `main.py` still calls it during FastAPI shutdown. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/hosted/internal/hosted.py#L18-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/hosted/internal/hosted.py#L23-L44) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/hosted/internal/hosted.py#L47-L56) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/main.py#L48-L55)

The long-standing hazard is unchanged: the cache is process-global and still carries a `TODO(multitenant)` warning because the first tenant to warm a hosted agent can bias the cached entry. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/hosted/internal/hosted.py#L35-L43)

## Oncall interrupt state

Oncall interrupt and resume state still lives in LangGraph’s `InMemorySaver`, which is durable only for a single process lifetime. The public module still warns that this is wrong for shared deployment mode, and `oncall_configured()` keeps the domain disabled there. [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/oncall/internal/graph.py#L21-L24) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/oncall/internal/graph.py#L88-L115) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/oncall/public.py#L10-L14) [Source](https://github.com/ruinosus/foundry-assured/blob/8e5fef809b476602ff31f4821f13e5bb18b64830/apps/backend/app/modules/oncall/public.py#L26-L33)

## When to edit this page

Consult this page when changing:

- conversation storage format, history replay, or citation persistence;
- usage accounting hooks or route-level conversation binding;
- durable ticket storage or hosted-client cache lifecycle;
- any stateful runtime where losing ordering or dedupe changes externally visible behavior.

For source-confirmation reads, continue in Knowledge Pipeline. For frontend replay behavior, continue in Assurance Console.

## Focused tests and validation

Start with:

- `cd apps/backend && uv run pytest tests/conversations/citations_persisted_test.py`
- `cd apps/backend && uv run pytest tests/conversations/duplicate_response_test.py`
- `cd apps/backend && uv run pytest tests/conversations/provider_invoked_test.py`

Conditional follow-up checks:

- `cd apps/backend && uv run pytest tests/conversations/provider_invoked_test.py tests/conversations/langgraph_recording_test.py` when changing conversation binding or middleware seams,
- `cd apps/backend && uv run pytest tests/tenancy/memory_scope_test.py tests/tickets/store_path_test.py` when a change crosses memory or ticket persistence boundaries.
