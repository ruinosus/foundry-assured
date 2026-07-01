# STEP 0 findings — grounded structured citations (verified live 2026-07-01)

**Verdict: GO** on the core (shape + no-403 + citations). Two sub-items are **DEFERRED-BLOCKED** on
inputs the environment doesn't have yet (test users / ACL corpus / a browser) — they do NOT block
Chunks 1 & 3 (the non-ACL bridge + frontend). Verified by `apps/backend/eval/step0_grounded_citations_spike.py`
run live against `cockpit-kb` on the `aapsample` azd env, as the signed-in user.

## What was proven

### ✅ (shape) A1 inline — no project connection needed; MCP primary auth via the `authorization` field
The Responses call is **fully inline** — `responses.create(model=…, input=…, instructions=…, tools=[mcp_tool], stream=…)`
with the KB as an inline MCP tool. **No `RemoteTool` project connection is required** (A1, not A2).
The MCP server (Azure Search KB) needs its **own primary auth**, supplied as the tool's **`authorization`**
field = a **search-scoped bearer** (`https://search.azure.com/.default`, i.e. Search Index Data Reader):

```python
mcp_tool = {
    "type": "mcp",
    "server_label": "knowledge-base",
    "server_url": f"{search_endpoint}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview",
    "allowed_tools": ["knowledge_base_retrieve"],
    "require_approval": "never",
    "authorization": <search-scoped bearer token>,          # PRIMARY auth to the MCP server (required)
    # "headers": {"x-ms-query-source-authorization": <user search token>},  # per-user ACL (Cockpit) — see (c)
}
resp = await client.responses.create(model=cfg.foundry_model, input=q, instructions=CITE, tools=[mcp_tool], stream=True)
```

- **`model` is REQUIRED** (the inline path has no agent to bind it): pass `cfg.foundry_model`.
- Error progression that pinned this down: no `model` → 400 "Missing required parameter: 'model'";
  no `authorization` → 400 `tool_user_error` "Authentication failed when connecting to the MCP server …
  401 (Unauthorized)"; with `authorization` = search token → **200 + grounded answer + citations**.

### ✅ (b) no 403 on raw inference under a user token
The user token ran `/responses` cleanly (the MI-service-principal 403 does not apply to a user). Confirms
the spec's core premise and the OBO path.

### ✅ (a) citations are structured AND real — better than the spec assumed
The response carries **both**:
1. **Inline markers** `【message_idx:search_idx†source_name】` in `output_text` (e.g. `【6:2†source】`) — the
   doc's format, present because the instructions asked for them. `inline 【…†…】 markers present: True`.
2. **Structured `url_citation` annotations** on the message content, shape:
   `{ "type": "url_citation", "start_index": int, "end_index": int, "title": str, "url": str }`.
   **The URLs are REAL blob URLs** (e.g. `https://stassured….blob.core.windows.net/cockpit-corpus/cockpit-mcp-server-v1.4.0__page-1.md`)
   — NOT the MCP-endpoint fallback the docs warned about (that warning applies to *search-index* knowledge
   sources; our cockpit corpus is **blob-backed**, so real doc URLs come back). The only pseudo-cites are
   `mcp://answersynthesis/` (the synthesis step) — **filter those out**.

**Annotation → `sources` mapping (for `grounded.py`), verified:**
```
annotation {type:"url_citation", title, url, start_index, end_index}
  → drop if url startswith "mcp://"        # synthesis pseudo-cite
  → { index: 1-based (dedup by url), source: url.rsplit("/",1)[-1], url: url }
```
The spike produced a clean deduped 8-source projection (real filenames + URLs). `content` (retrieved
snippet) is NOT on the annotation — it lives in the `knowledge_base_retrieve` tool-call result in
`output[]`; wire content-on-click as a stretch (v1 = filename + url footnote).

**Frontend note:** the blob URLs are **private storage** (opening them directly may 401 for the browser
user). So v1 click behavior = show the source filename + (optionally) the retrieved snippet; a direct
link needs a SAS or a backend proxy — out of scope for the PoC.

## Deferred-blocked (do NOT block Chunks 1 & 3)

### ⏸ (c) ACL trim — blocked on inputs
`cockpit-kb` here was ingested WITHOUT permission metadata, and the env has no `COCKPIT_TEST_USER_A/B`,
no `COCKPIT_ACL_*_GROUP` object-ids, and no `COCKPIT_DOCBUNDLES` corpus path. So the
`x-ms-query-source-authorization` trim (Chunk 2 + Chunk 4 A-vs-B) can't be verified yet. The header slot
is confirmed (spec §8 + the `secure_search.py` usage); trimming-on-our-service-version stays UNVERIFIED
until those inputs exist. **Contingency unchanged:** if it doesn't trim, keep the app-side trim (spec §5).

### ⏸ (frontend channel) — needs the app + a browser
Whether CopilotKit v2 `useAgent` surfaces a CUSTOM `sources` event vs. needs the message-trailer fallback
is unverified. Lower risk: the annotations are **standard OpenAI `url_citation`** objects, which often flow
through the assistant message itself — Chunk 3 confirms the delivery channel in the browser.

## Impact on the plan/spec (apply before Chunk 1)
- **A1 confirmed** → drop the A2/project-connection prerequisite from the critical path (keep as a note).
- **`build_responses_kwargs` must include** `model` and the `authorization` (search token) field; the ACL
  `headers` entry stays conditional on `domain.acl`.
- **Citation URLs are real** → the frontend can show a filename + url footnote (revise the §8 "falls back to
  MCP endpoint" caveat to "applies to search-index sources; our blob corpus returns real URLs").
- Annotation type is **`url_citation`** (standard), in addition to the inline `【…†…】` markers.
