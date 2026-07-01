# Grounded agents — structured citations via OBO + Responses API + Foundry IQ MCP tool

**Status:** design (approved in brainstorming; pending spec review + a web-verification of the
Microsoft pattern + user review before the implementation plan).

**Goal (one sentence).** Make the grounded agents (Cockpit, Selfwiki) return **structured,
clickable citations** — the Microsoft-indicated way — while enforcing **per-user document-level
ACL**, by calling the **Responses API on-behalf-of the signed-in user** with the knowledge base
attached as a **Foundry IQ MCP tool**, replacing today's regex-from-text source extraction.

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

**Hard requirement (user decision):** per-user document-level **ACL** must be preserved (as the old
live `/cockpit` did via OBO). The Microsoft docs are explicit: *"Foundry Agent Service doesn't support
per-request headers for MCP tools [in preview]… For per-user authorization, use the Azure OpenAI
Responses API instead"* — with the `x-ms-query-source-authorization` header carrying the user's token.

## 2. Approach (chosen: **A — OBO + direct Responses API + inline MCP knowledge tool**)

Per request, the grounded endpoint calls the **Responses API directly as the user (OBO)** with the KB
attached as an inline **Foundry IQ MCP tool** and the user's search token as the ACL header. One call
does **agentic retrieval (ACL-trimmed) + generation + citations**. This is the only approach that
satisfies all three requirements at once:

| | MI hosted (today) | **A: OBO + Responses + MCP tool** |
|---|---|---|
| Raw inference | 403 | ✅ (user token) |
| Per-user ACL | ✗ | ✅ `x-ms-query-source-authorization` |
| Structured citations | ✗ (context provider) | ✅ MCP `knowledge_base_retrieve` |

**Rejected:** *B — Foundry agent + MCP tool via a RemoteTool project connection* (the doc's agent path):
no per-request ACL header in preview → fails the ACL requirement. *C — keep the context provider, parse
the stream*: emits no annotations → nothing to parse.

**Two OBO tokens** (the OBO machinery already exists in `app/core/auth.py` + `app/agents/secure_search.py`):

| Token | Scope | Purpose |
|---|---|---|
| model | `https://ai.azure.com/.default` | run the Responses call **as the user** → no 403 |
| search | `https://search.azure.com/.default` | `x-ms-query-source-authorization` header → per-user ACL |

Responses call shape (signatures/annotation fields confirmed in **STEP 0** — this is preview):

```python
client(<user OBO for ai.azure.com>).responses.create(
    input=<messages>,
    instructions=<DOMAIN_INSTRUCTIONS + directive to use the KB tool and cite with 【idx†source】>,
    tools=[{
        "type": "mcp",
        "server_label": "knowledge-base",
        "server_url": f"{search_endpoint}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview",
        "allowed_tools": ["knowledge_base_retrieve"],
        "require_approval": "never",
        "headers": {"x-ms-query-source-authorization": <user OBO for search.azure.com>},
    }],
    stream=True,
)
```

The grounded agents' `AzureAISearchContextProvider` and the manual `secure_search.py` trim **go away**
for these domains — ACL becomes the header's responsibility (the Microsoft way).

## 3. Components & data flow

- **`app/services/grounded.py` → `stream_grounded_agui(body, domain_cfg, user)`** (new). Does the two
  OBO exchanges, builds the Responses call (§2), consumes the stream and **re-emits AG-UI**:
  - `response.output_text.delta` → `TextMessageContentEvent` (text, including the inline `【idx†source】` markers).
  - annotation events (`response.output_text.annotation.added` / the References list) → collect citations.
  - on completion → emit an AG-UI **`CUSTOM`** event `{name:"sources", value:[{index, source, url?, content?}]}` + `RunFinished`.
  - Mirrors the hosted `stream_agui` bridge shape, but **live + OBO + MCP tool + citations**.
- **Mounting change.** `/cockpit` and `/selfwiki` move **off** the agent-framework AG-UI adapter and
  become **router endpoints** (like `/helpdesk-hosted`) that call `stream_grounded_agui`. The frontend
  is unchanged here — `route.ts` already registers these domains as plain `HttpAgent`s to `/cockpit` /
  `/selfwiki`, which now stream the custom AG-UI.
- **Frontend citations** (the Microsoft UI pattern = inline markers + footnotes):
  - `EvidencePanel` subscribes to the `sources` `CUSTOM` event → **structured, numbered, clickable
    footnotes**; click → `url` opens it, else `content` expands/modal, else the source name. **This is
    the guaranteed primary channel and delivers the "click a source → show it" request.**
  - Inline `【idx†source】` markers in the message text → transform to clickable `[1]` superscripts
    **if `CopilotChat` allows a custom markdown/render component** (stretch); if not, strip the raw
    markers and rely on the footnotes.

## 4. Scope, rollout & the fate of the interim hosted twins

- **In scope:** the **grounded** domains (`kind:"grounded"`) — **Cockpit** and **Selfwiki**.
- **PoC:** Cockpit first (prove citations + ACL + no 403 end to end) → **rollout:** Selfwiki (same
  code path, its own KB).
- **Helpdesk (workflow):** OUT. It's `triage→retrieve→resolve→HITL`, not grounded; its live path 403s
  (MI), so it keeps the **hosted toggle**. The same OBO insight could later fix the workflow's model
  calls — a **future slice**, not this one.
- **Hosted twins (`cockpit-expert`, `selfwiki-expert`):** the live-OBO path makes them redundant for
  grounded. But the MCP tool is **preview**, so **keep them as a fallback this slice** (the Live/Hosted
  toggle stays; Live now works). Retire them in a later cleanup once OBO is proven solid.

## 5. ACL prerequisite (dependency), STEP 0 gate & testing

### ACL prerequisite (must be in the plan)
For `x-ms-query-source-authorization` to trim, the KB's search index must carry **permission metadata
fields** on the documents. **`cockpit-kb` was ingested WITHOUT them** (the aap-kb manifests have
`groups: None`, no classification, and `ingest_cockpit` only stamps ACL when `acl_group_map` is set).
So the ACL requirement adds a **prerequisite task: re-ingest with permission metadata fields**, which
needs a **classification** (which groups each doc belongs to). For the **PoC**, use a **minimal
classification** — enough to prove *A sees confidential / B doesn't* (e.g., default to a group + mark
one doc `confidential`); a real classification of the 23 components is a rollout concern.
See `app/knowledge/acl_setup.py`, `ingest_cockpit.py`, and the [document-level access docs](https://learn.microsoft.com/en-us/azure/search/search-document-level-access-overview).

### STEP 0 — verification gate (rule #1; blocks all implementation)
A read-only spike calling the Responses API directly (user/OBO) with the inline MCP tool + the
`x-ms-query-source-authorization` header, proving **(a)** citations/annotations come back (capture the
exact structure + fields → feeds §2/§3), **(b)** no 403 (user token), **(c)** the header **trims by
ACL**. No green here → no build. (Mirrors the D-packaging "Task 0" pattern.)

### Testing
- **E2E** (the existing `e2e/` Playwright harness, autonomous MFA): Cockpit (Live) → structured,
  clickable citations, no 403. The **real ACL round-trip**: `cockpit-test-a` (all groups) **vs**
  `cockpit-test-b` (public-only) → **B sees fewer sources than A** (the per-user ACL proof).
- **Backend** (repo convention: runnable `def main()->int` in `apps/backend/eval/`, no pytest):
  infra-free = `stream_grounded_agui` builds the correct Responses payload (MCP tool config + the two
  OBO tokens) without calling Azure; infra-gated = STEP 0 + the ACL round-trip.
- **Success:** 🟢 Cockpit answers grounded, citations clickable → content, no 403, **A sees confidential
  / B doesn't**. 🔴 empty citations / 403 / B sees confidential.

## 6. Constraints & non-goals

- **Rule #1** — no invented SDK signatures. `azure-ai-projects` 2.2.0 is confirmed to expose
  `PromptAgentDefinition` + `MCPTool`; the exact Responses-tool/annotation shapes are confirmed in
  STEP 0 (the API is `2026-05-01-preview`).
- **Rule #2** — keyless / OBO; no API keys.
- **self_hosted byte-identical** where applicable; per-tenant config via `tenant_config()`.
- **Non-goals:** the Helpdesk workflow; retiring the hosted twins; a full 23-component ACL
  classification (PoC uses a minimal one).

## 7. Open questions / risks

- **STEP 0 is the make-or-break** — the preview Responses+MCP-tool+ACL-header behaviour must be
  verified live; if annotations don't come back or the ACL header doesn't trim, the approach changes.
- **Inline `[1]` markers** depend on `CopilotChat` render customization (stretch, decided in impl).
- **Preview API** (`2026-05-01-preview`) — no SLA; the hosted-twin fallback mitigates.
- The **Microsoft-pattern web verification** (requested by the user) runs after the spec review, before
  user review — to confirm the whole OBO + Responses + MCP-tool + ACL-header approach is what Microsoft
  indicates.
