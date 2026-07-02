# Grounded agents — structured citations via OBO + Responses API + Foundry IQ MCP tool

**Status:** design — **Microsoft-pattern verified** (§8) + spec-reviewed; pending user review before
the implementation plan.

**Goal (one sentence).** Make the grounded agents (Cockpit, Selfwiki) return **structured,
clickable citations** — the Microsoft-indicated way — while enforcing **per-user document-level
ACL** (Cockpit), by calling the **Responses API on-behalf-of the signed-in user** with the knowledge
base attached as a **Foundry IQ MCP tool** (`knowledge_base_retrieve`), replacing today's
regex-from-text source extraction.

> **A note on confidence.** Every SDK/stream/annotation shape in §2–§3 is **STEP-0-provisional**
> (marked `⟨S0⟩`) — the API is `2026-05-01-preview` (rule #1). STEP 0 (§5) is the gate that turns
> each `⟨S0⟩` into a fact before any implementation. §8 records what Microsoft's docs *do* confirm.

---

## 1. Problem / context

The `EvidencePanel` derives "sources" by running a **regex over the answer text** — a v1 hack. We
want real citations. Verified in-session:

- Today the grounded agents use `FoundryChatClient.as_agent(context_providers=[AzureAISearchContextProvider(mode="agentic")])`.
  The provider **injects retrieved docs as context** (prose citations), so the Responses output
  carries **empty `annotations`** (tested the `cockpit-expert` endpoint: `output_text.annotations = None`).
- The container **managed identity 403s on raw model inference** (Foundry data-plane doesn't honor a
  service principal there — a platform behavior, tracked in [`docs/MICROSOFT-ALIGNMENT.md`](../../MICROSOFT-ALIGNMENT.md)),
  which is why the grounded agents currently answer via a **hosted twin**.
- A **user token (OBO) works on raw inference** (proven: 200), so the per-user path is *not* blocked
  by the 403.

**Hard requirement (user decision):** per-user document-level **ACL** must be preserved for Cockpit
(as the old live `/cockpit` did via OBO). Microsoft is explicit (§8): the per-user-auth path **is** the
Responses API, with the `x-ms-query-source-authorization` header carrying the user's search token.

## 2. Approach (chosen: **A — OBO + direct Responses API + MCP knowledge tool**)

Per request, the grounded endpoint calls the **Responses API as the user (OBO)** with the KB attached
as a **Foundry IQ MCP tool** (`knowledge_base_retrieve`) and the user's search token as the ACL header.
One call does **agentic retrieval (ACL-trimmed) + generation + citations**. It's the only approach that
satisfies all three requirements at once, and it's the path Microsoft names for per-user auth (§8):

| | MI hosted (today) | **A: OBO + Responses + MCP tool** |
|---|---|---|
| Raw inference | 403 | ✅ (user token) |
| Per-user ACL | ✗ | ✅ `x-ms-query-source-authorization` |
| Structured citations | ✗ (context provider) | ✅ MCP `knowledge_base_retrieve` |

**Rejected:** *B — Foundry **agent** + MCP tool via a RemoteTool project connection* (the doc's default
agent path): in preview it **can't set per-request headers**, so it can't carry a per-user ACL token —
Microsoft itself redirects this case to the Responses API (§8). *C — keep the context provider, parse
the stream*: emits no annotations → nothing to parse.

**Two auth layers on the MCP tool (⟨S0⟩ — the central unknown).** Microsoft's query-time-ACL doc says
document visibility requires **both** (a) the *calling app's* RBAC role (**Search Index Data Reader**)
as the tool's primary auth, **and** (b) the *user* identity via `x-ms-query-source-authorization`.
That raises the one shape question STEP 0 must settle: in the Responses **inline** MCP path, is the
primary (a) auth satisfied by a **RemoteTool project connection** (`project_connection_id`, as the agent
path uses) or by the caller — and can (b) be a **per-request** header there? Two candidate shapes:

- **A1 (preferred): fully inline** — `responses.create(tools=[{type:"mcp", server_url, headers:{x-ms-query-source-authorization: <user search token>}}])`, no agent, header per-request. Requires primary (a) auth to reach the MCP endpoint — STEP 0 confirms whether a project connection is still needed.
- **A2 (fallback): agent + project connection**, invoked via Responses with the user header injected per-request if the preview allows it.

If A1 needs a **RemoteTool project connection**, that's a **control-plane prerequisite** (script/ADR,
`authType=ProjectManagedIdentity`, `audience=https://search.azure.com/`, `target={search}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview`) — same as the ACL re-ingest (§5).

**Two OBO tokens** (the search-scope exchange already exists in `app/agents/secure_search.py` via
`credential_for_request().get_token("https://search.azure.com/.default")`; the model-scope OBO is a
**new use** — see the wiring note below):

| Token | Scope | Purpose |
|---|---|---|
| model ⟨new⟩ | `https://ai.azure.com/.default` | run the Responses call **as the user** → no 403 |
| search ⟨exists⟩ | `https://search.azure.com/.default` | `x-ms-query-source-authorization` header → per-user ACL |

**OBO wiring (issue #3).** The `/cockpit` `/selfwiki` router endpoints run **outside** the
agent-framework adapter, so `stream_grounded_agui` must obtain both tokens from the **request-scoped**
credential. STEP 0 confirms that `current_user()` / `credential_for_request()` are populated in the
router-endpoint request context (the auth middleware runs before the route) and that
`credential_for_request()` can mint an `ai.azure.com` token there (today only the search scope is
exchanged). The model-scope OBO exchange is added to `app/core/auth.py` (or `grounded.py`) — no invented
signature; it reuses the existing OBO exchange with a different scope.

Responses call shape — **all fields ⟨S0⟩**, annotation marker is Microsoft's verified format (§8):

```python
# ⟨S0⟩ exact tool dict + whether project_connection_id is required is confirmed in STEP 0
client(<user OBO for ai.azure.com>).responses.create(
    input=<messages>,
    instructions=<DOMAIN_INSTRUCTIONS
        + "Every answer must provide annotations for the knowledge base tool and render them as"
          " 【message_idx:search_idx†source_name】; if not found, say you don't know.">,
    tools=[{
        "type": "mcp",
        "server_label": "knowledge-base",
        "server_url": f"{search_endpoint}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview",
        "allowed_tools": ["knowledge_base_retrieve"],   # the only supported KB MCP tool (§8)
        "require_approval": "never",
        "headers": {"x-ms-query-source-authorization": <user OBO for search.azure.com>},  # ACL, cockpit only
        # "project_connection_id": <conn>,   # ⟨S0⟩ include iff A1 needs the primary-auth connection
    }],
    stream=True,
)
```

For the grounded domains, the `AzureAISearchContextProvider` and the manual `secure_search.py`
app-side trim are **replaced** — ACL becomes the header's responsibility (the Microsoft way) —
**subject to the STEP 0(c) contingency in §5** (don't delete the app-side trim until the header is
proven to trim on our service version).

## 3. Components & data flow

- **`app/services/grounded.py` → `stream_grounded_agui(body, domain_cfg, user)`** (new). Does the OBO
  exchange(s), builds the Responses call (§2), consumes the stream and **re-emits AG-UI** (mirrors the
  hosted `stream_agui` bridge, but live + OBO + MCP tool + citations):
  - text deltas ⟨S0⟩ (`response.output_text.delta`) → `TextMessageContentEvent`.
  - annotation events ⟨S0⟩ (`…annotation.added` / the `References:` list) → collect citations.
  - on completion → an AG-UI **`CUSTOM`** event `{name:"sources", value:[{index, source, url?, content?}]}` + `RunFinished`.
  - **`domain_cfg` shape (issue #7):** `{kb_name, instructions, acl: bool}`. `acl=True` (Cockpit) →
    attach the search-OBO header; `acl=False` (Selfwiki — single-audience, **no permission metadata**,
    per its own docstring) → **omit** the header entirely. The header is **conditional**, not unconditional.
- **Mounting change (issue #6).** `/cockpit` and `/selfwiki` move **off** the agent-framework AG-UI
  adapter (in `app/main.py`) and become **router endpoints** (like `/helpdesk-hosted`) that call
  `stream_grounded_agui`. Consequently `build_cockpit_agent()` / `build_selfwiki_agent()` and their
  `SecureAzureAISearchProvider` are **no longer used by the live path**; the plan states explicitly, per
  file, whether each is **deleted** or **kept only for the hosted twins' build** (the twins use the
  separate `apps/hosted-*` build, so the in-repo `build_*_agent` likely becomes dead for live → remove,
  unless STEP 0(c) forces the app-side-trim fallback, in which case a trimmed variant is retained).
  The frontend is unchanged — `route.ts` already registers these domains as plain `HttpAgent`s to
  `/cockpit` / `/selfwiki`.
- **Frontend citations** (Microsoft's UI pattern = inline markers + a References/footnotes list):
  - `EvidencePanel` renders the `sources` `CUSTOM` event → **structured, numbered, clickable footnotes**.
    **⚠️ click→display uses `content` (the retrieved text), not `url`:** Microsoft notes that
    **search-index knowledge sources return a citation URL that falls back to the MCP endpoint** (not a
    real document URL) (§8) — so a modal/expander over the annotation's **text** is the reliable
    "click a source → show it"; a `url` is used only when a source actually provides one (e.g. blob KBs).
  - **⟨S0-frontend⟩ delivery is not yet proven (issue #1).** `EvidencePanel.tsx` today subscribes only
    to `agent.subscribe({onMessagesChanged, onRunFinalized})` and reads `agent.messages`; there is **no
    evidence CopilotKit v2 `useAgent` surfaces an AG-UI `CUSTOM` event**. STEP 0 includes a **frontend
    sub-gate**: emit one backend `CUSTOM` `sources` event and prove it is **observably reachable** from
    `useAgent` in the browser through the real CopilotKit runtime + `route.ts`. If it is **not**
    reachable, the fallback is to carry citations as a **structured trailer in the assistant message**
    (parsed from `agent.messages`, which the panel already reads) — decided by STEP 0, not assumed.
  - Inline `【message_idx:search_idx†source_name】` markers in the text → clickable `[1]` superscripts
    **if `CopilotChat` allows a custom markdown/render component** (stretch); else strip the raw markers
    and rely on the footnotes.

## 4. Scope, rollout & the fate of the interim hosted twins

- **In scope:** the **grounded** domains (`kind:"grounded"`) — **Cockpit** (with ACL) and **Selfwiki**
  (no ACL).
- **PoC:** Cockpit first (prove citations + ACL + no 403 end to end) → **rollout:** Selfwiki (same code
  path, its own KB, `acl=False`).
- **Helpdesk (workflow):** OUT. It's `triage→retrieve→resolve→HITL`, not grounded; its live path 403s
  (MI), so it keeps the **hosted toggle**. The same OBO insight could later fix the workflow's model
  calls — a **future slice**, not this one.
- **Hosted twins (`cockpit-expert`, `selfwiki-expert`):** the live-OBO path makes them redundant for
  grounded. But the MCP tool is **preview**, so **keep them as a fallback this slice** (the Live/Hosted
  toggle stays; Live now works). Retire them in a later cleanup once OBO is proven solid.

## 5. STEP 0 gate, the ACL prerequisite & testing

### STEP 0 — verification gate (rule #1; blocks all implementation)
A read-only spike, no product code shipped, proving each `⟨S0⟩`:
- **(shape)** the exact Responses inline-MCP-tool dict + **whether a RemoteTool project connection is
  required** (A1 vs A2), and the **model-scope OBO** works from the router-endpoint request context.
- **(a) citations** — annotations/`References:` come back; **capture the exact structure + produce the
  concrete `annotation → {index, source, url, content}` mapping** (this is a STEP 0 **exit artifact**,
  feeding §2/§3; without it the plan would guess SDK shapes — rule #1).
- **(b) no 403** — the user/OBO model token runs raw inference (expected per the in-session 200).
- **(c) ACL trims** — the `x-ms-query-source-authorization` header **trims by document on our service
  version**. Microsoft records a **Nov-2025 behavior change** making the filter apply even with service
  auth, and *"if the user token is omitted, only public documents are returned"* (§8) — but
  `secure_search.py` documents the header as *"inert today on our service version,"* which may predate
  that change. **Contingency (issue #5):** if (c) shows the header does **not** trim, the app-side trim
  (`secure_search.py` layer B) **cannot be deleted** and the "simplification" in §2/§3 is void — retain
  a trimmed grounded variant instead.
- **(frontend)** the `CUSTOM` `sources` event is reachable from `useAgent` (issue #1) — else adopt the
  message-trailer fallback (§3).

No green on (a)+(b)+(c)+(frontend) → no build. (Mirrors the D-packaging "Task 0" pattern.)

### ACL prerequisite (dependency; Cockpit only)
For `x-ms-query-source-authorization` to trim, the KB's index must carry **permission metadata fields**
in **`filterable` string fields**, holding POSIX-style ACLs / group IDs (§8). **`cockpit-kb` was
ingested WITHOUT them** (the aap-kb manifests have `groups: None`; `ingest_cockpit` only stamps ACL when
`acl_group_map` is set). So the ACL requirement adds a **prerequisite task: re-ingest cockpit-kb with
permission metadata fields** + a **minimal classification** — for the PoC, enough to make the A-vs-B
test meaningful (below); a full 23-component classification is a rollout concern.
See `app/knowledge/acl_setup.py`, `ingest_cockpit.py`, and the [document-level access docs](https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview).

### Testing
- **The ACL round-trip fixture must be concrete (issue #4).** Classify so that **one specific document
  is confidential** (group A only) and the rest are public. Pick an **E2E query whose top-relevant answer
  lives in that confidential doc.** Then: `cockpit-test-a` (in group A) grounds on the confidential doc
  and **cites it**; `cockpit-test-b` (public-only) asks the **same query** and **does not** see that doc
  — it either grounds on public docs with **fewer/different citations** or declines. Success is
  **B-lacks-the-confidential-citation-that-A-has**, not merely "B sees fewer" (which a trivial decline
  could fake). Grounded in Microsoft's *"if the user token is omitted, only public documents are
  returned"* (§8).
- **E2E** (`e2e/` Playwright, autonomous MFA): Cockpit (Live) → structured, clickable citations
  (click → content), no 403; then the A-vs-B round-trip above.
- **Backend** (repo convention: runnable `def main()->int` in `apps/backend/eval/`, no pytest):
  infra-free = `stream_grounded_agui` builds the correct Responses payload (MCP tool config, the
  conditional ACL header per `domain_cfg.acl`, the two OBO scopes) without calling Azure; infra-gated =
  STEP 0 + the ACL round-trip.
- **Success:** 🟢 Cockpit answers grounded, citations clickable → content, no 403, **A cites the
  confidential doc / B doesn't**; Selfwiki answers grounded with citations, **no ACL header**. 🔴 empty
  citations / 403 / B sees the confidential doc.

## 6. Constraints & non-goals

- **Rule #1** — no invented SDK signatures. The **agent-path** SDK shapes (`PromptAgentDefinition`,
  `MCPTool`, `project_connection_id`) are confirmed in Microsoft's doc (§8) but belong to rejected
  Approach B; **Approach A's inline `responses.create(tools=[{type:"mcp",…}])` shape is
  STEP-0-provisional** (do not treat it as verified until STEP 0(shape) is green).
- **Rule #2** — keyless / OBO; no API keys.
- **self_hosted byte-identical** where applicable; per-tenant config via `tenant_config()`.
- **Non-goals:** the Helpdesk workflow; retiring the hosted twins; a full 23-component ACL
  classification (PoC uses a minimal one); elevated-read debugging (`x-ms-enable-elevated-read`
  **doesn't work on `knowledge_base_retrieve`** per §8, so it's not a debugging tool here).

## 7. Open questions / risks

- **STEP 0 is make-or-break** — the preview Responses+MCP-tool+ACL-header behaviour (shape, (a), (b),
  (c), frontend) must be verified live; a red on any changes the approach.
- **The A1-vs-A2 shape** (inline vs project-connection) is unresolved until STEP 0(shape); it decides
  whether a control-plane project-connection prerequisite exists.
- **ACL-header staleness** — the `secure_search.py` "inert" note vs Microsoft's Nov-2025 change; STEP
  0(c) is the tiebreaker, with the app-side-trim contingency as the safety net.
- **Frontend CUSTOM-event delivery** (issue #1) — message-trailer fallback if unreachable.
- **Preview API** (`2026-05-01-preview`) — no SLA; the hosted-twin fallback mitigates.

## 8. Microsoft-pattern verification (the proof)

Web-verified on 2026-07-01 against `learn.microsoft.com` (this is the artifact answering *"does Microsoft
indicate this?"*). Recorded as rows in [`docs/MICROSOFT-ALIGNMENT.md`](../../MICROSOFT-ALIGNMENT.md).

- **The per-user-auth path IS the Responses API — verbatim** ([Connect agents to Foundry IQ KBs](https://learn.microsoft.com/en-us/azure/foundry/agents/how-to/foundry-iq-connect)):
  *"In this preview, Foundry Agent Service doesn't support per-request headers for MCP tools. Headers set
  in agent definitions apply to all invocations and can't vary by user or request. **For per-user
  authorization, use the Azure OpenAI Responses API instead.**"* → validates choosing A over B.
- **KB attaches as the `knowledge_base_retrieve` MCP tool** — *"Azure AI Search knowledge bases expose
  the `knowledge_base_retrieve` MCP tool… the only tool currently supported."* Endpoint =
  `{search}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview`; `require_approval="never"`.
- **The annotation format is Microsoft's** — instructions render citations as
  `【message_idx:search_idx†source_name】`; responses return a `References:` list. (Corrected our earlier
  `【idx†source】`.)
- **Citation URL caveat** — *"search index knowledge sources fall back to the MCP endpoint"* for the
  citation URL → the frontend click-through uses the retrieved **content**, not a doc URL (§3).
- **Per-user ACL header + prerequisite** ([Query-time ACL & RBAC enforcement](https://learn.microsoft.com/en-us/azure/search/search-query-access-control-rbac-enforcement)):
  *"pass user tokens via the `x-ms-query-source-authorization` header at query time to filter results
  based on the user's identity"*; requires **permission metadata in `filterable` string fields**; needs
  **both** the app's **Search Index Data Reader** role **and** the user header; **fail-closed** —
  *"If ACL evaluation fails… returns 5xx and does not return a partially filtered result set"*; and
  *"if the user token is omitted, only public documents… are returned"* (the basis for the A-vs-B test).
- **Nov-2025 change** — ACL filters now apply even under service auth; relevant to the `secure_search.py`
  "inert" note (STEP 0(c) confirms on our service version).
