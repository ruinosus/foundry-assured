# STEP 0 findings — native-retriever group-filter probe (grounded-archetype unification gate)

**Date:** 2026-07-01
**Probe:** `apps/backend/eval/step0_native_filter_probe.py` (throwaway verification spike, run live)
**Gate question:** Does the NATIVE Foundry IQ retriever (the agentic `knowledge_base_retrieve` / KB
`retrieve` API) honor a **caller-supplied group FILTER** — an explicit OData filter over the stamped
`groups` field, applied at retrieval time — as a per-user ACL mechanism? (Distinct from the automatic
`x-ms-query-source-authorization` header, which the agentic path does NOT honor — azure-sdk-for-python#44454.)

---

## VERDICT: ❌ NO — the native retriever does NOT expose a caller filter on this KB.

Fall back to **Plan B (direct-search)** for the cockpit per-user-ACL path: a direct `POST
{search}/indexes/{index}/docs/search` as the user, trimmed by the `x-ms-query-source-authorization`
header over the stamped `groups` field (`permissionFilter=groupIds`, `permissionFilterOption=enabled`),
then synthesize from only the authorized docs. This is exactly what `app/services/grounded.py`
`_direct_search_authorized` already does. **No change to the acl=True path is warranted.**

Empirically observed, not inferred.

---

## The mechanism that DOES exist (docs) and WHY it doesn't apply here

Microsoft docs (`learn.microsoft.com/azure/search/agentic-retrieval-how-to-retrieve`, updated 2026-06-29)
DO define a caller filter for the KB retrieve API:

```
POST {search}/knowledgebases/{kb}/retrieve?api-version=2026-05-01-preview
{
  "messages": [ {role:assistant,…}, {role:user,…} ],
  "knowledgeSourceParams": [
    { "knowledgeSourceName": "<ks>", "kind": "searchIndex", "filterAddOn": "<OData filter>" }
  ]
}
```

`filterAddOn` is an OData expression **AND-combined** with any persisted base filter (it can only NARROW).
**BUT the docs state — and the live service confirms — `filterAddOn` is valid for `kind: "searchIndex"`
knowledge sources ONLY.** It is rejected on every other source kind.

**This KB's knowledge source is `azureBlob`, not `searchIndex`** (discovered live from the KB def):

- KB `cockpit-kb` → knowledge source `cockpit-docbundles-ks`, `kind = "azureBlob"`.
- Other sources in the service: `helpdesk-runbooks-ks`, `selfwiki-docbundles-ks` (kinds not probed;
  the cockpit source is the one that needs per-user ACL).

So the caller-filter surface the docs describe does not apply to the source backing this KB.

## Exact errors observed (all three api-versions, verbatim)

Service credential = app/dev identity (`DefaultAzureCredential`, Search Index Data Reader); no
`x-ms-query-source-authorization` header (the point is the filter, not the header).

| api-version         | source kind | status | result |
|---------------------|-------------|--------|--------|
| `2026-05-01-preview`| azureBlob   | 400    | `InvalidRequestParameter`: *"Invalid parameters for polymorphic discriminator 'kind' with value 'azureBlob'. Property 'filterAddOn' is not allowed."* |
| `2025-11-01-preview`| azureBlob   | 400    | same rejection: *"Property 'filterAddOn' is not allowed"* |
| `2026-04-01`        | azureBlob   | 400    | *"The parameter 'messages' in the request payload is not a valid parameter"* — the GA `2026-04-01` uses the OLDER `intents` request schema (not `messages`), so it's a shape mismatch, not filter acceptance. |

A control run (same request, `filterAddOn` omitted, `kind: "azureBlob"`) returns **HTTP 200** with the
expected `{response, activity, references}` body — so the endpoint/auth/source-name are all correct; it is
specifically the `filterAddOn` property that is rejected for the `azureBlob` kind. (Sending
`kind: "searchIndex"` for this source is itself rejected: *"kind 'searchIndex' does not match the kind
'azureBlob' of knowledge source 'cockpit-docbundles-ks'."*)

## Captured native-path shape (for reference — the acl=**False** / non-ACL path only)

The retrieve API (`kind: azureBlob`, no filter) returns three components (api `2026-05-01-preview`):

- `response[]` — chat-style; `content[].text` is a JSON-encoded string of ranked chunks, each with
  `ref_id` / `title` / `terms` / `content` (the grounding string an LLM cites).
- `activity[]` — query plan: `modelQueryPlanning`, then one `azureBlob` entry per subquery with
  `azureBlobArguments.search` and `count`, then `agenticReasoning` / `modelAnswerSynthesis`.
- `references[]` — one per ranked doc: `{ type, id, activitySource, docKey, sourceData }`. `id` is a
  citation-local ref id (NOT the index doc key); `docKey` is the index doc key; `sourceData` (often
  `null` unless requested) can carry `title` / `content`.

**annotation → `{source, url, snippet}` mapping for the native path** (the product already implements
the equivalent for the *inline MCP tool* variant in `grounded.py` via `url_citation` annotations):
`references[].docKey` (or `sourceData.title`/`sourceData.blob_url`) → `source`;
`sourceData.blob_url` → `url` (private blob, opens 403 by design → carry `content` as inline snippet);
`sourceData.content` (or the matching `response[].content[].text` chunk by `ref_id`) → `snippet`.
This shape is **not** wired for the acl=True path — that stays on direct-search (see verdict).

## Index facts confirmed live (support the direct-search Plan B)

`cockpit-docbundles-ks-index`: field `groups` = `Collection(Edm.String)`, `filterable=true`,
`permissionFilter=groupIds`; index `permissionFilterOption=enabled`. So the direct-search header trim is
armed and correct — Plan B needs no index change.

## Implication for the next task

Build the grounded-archetype unification with **two retrieval archetypes**, as `grounded.py` already
splits them:

- **acl=False** (selfwiki, single-audience) → native agentic retrieval (inline MCP `knowledge_base_retrieve`
  tool / the KB retrieve API), native citations. No caller filter needed.
- **acl=True** (cockpit, per-user ACL) → **direct-search + synthesize** (Plan B). The native retriever
  cannot be handed a per-user filter for this `azureBlob`-backed KB, so per-user trimming stays on the
  direct `/docs/search` header path (`_direct_search_authorized`).

If a future KB is rebuilt on a **`searchIndex`** knowledge source, re-run this probe — `filterAddOn`
would then be accepted and the ✅ path (native retrieval + caller filter) could be revisited.

---

### Reproduce

```
cd apps/backend && uv run python -m eval.step0_native_filter_probe
```
Exit codes: `0` ✅ trim confirmed / SKIP · `1` filter ignored (leak) · `2` filter rejected on all versions
(**this run**) · `3` inconclusive. Skips cleanly (SKIP:, rc 0) when infra/ACL-group env is absent.
