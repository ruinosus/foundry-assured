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

---
---

# STEP 0.5 — searchIndex re-probe (the unification HARD GATE)

**Date:** 2026-07-01
**Probe:** `apps/backend/eval/step0_searchindex_filter_probe.py` (throwaway verification spike, run live)
**Gate question:** Does the native retriever's `filterAddOn` actually trim per-user (A vs B) when the KB's
knowledge source is `kind: "searchIndex"` over the EXISTING ACL-stamped `cockpit-docbundles-ks-index`?
STEP 0 left this open because the production `cockpit-kb` source is `azureBlob` (filterAddOn rejected there).

---

## VERDICT: ❌ for the LITERAL question (filterAddOn is NOT the per-user ACL lever) — but ✅ for the GOAL:

**native agentic retrieval + per-user ACL + a single head IS achievable on a `searchIndex`-backed KB — via
the `x-ms-query-source-authorization` HEADER, which the searchIndex retrieve path HONORS (unlike azureBlob
in STEP 0).** `filterAddOn` over the `groups` field is *accepted and applied* on `kind:searchIndex`, but it
is **inert as an ACL mechanism** on this index and must NOT be relied on for per-user trimming.

All observations below are **empirically observed live**, not inferred.

### The three empirical facts (from the probe run)

1. **`filterAddOn` IS accepted + applied on `kind:"searchIndex"`** (the STEP 0 `azureBlob` 400 "Property
   'filterAddOn' is not allowed" is gone). The filter is echoed verbatim into
   `activity[].searchIndexArguments.filter`, so the docs-inferred syntax is correct.
2. **The index's `permissionFilterOption=enabled` DOMINATES and makes `filterAddOn`-over-`groups` useless
   as ACL.** CONTRARY to the docs' claim ("Without the identity token, results from permission-enabled
   knowledge sources are returned **unfiltered**"), with **no** `x-ms-query-source-authorization` header the
   permission trim treats the caller as belonging to **no groups** and returns **ZERO** docs (`count:[0,0,…]`,
   fully fail-closed). So a `groups` filterAddOn can never surface a permission-gated doc — the permission
   trim zeroes the candidate set *before* the filter narrows it. (Verified independently via direct
   `/docs/search`: no header → 0 docs; `search=*` + any `groups` filter → still 0.)
3. **The searchIndex retrieve HONORS `x-ms-query-source-authorization`** (the key difference from STEP 0's
   azureBlob, where the agentic path ignored it — azure-sdk-for-python#44454). With the header, subqueries
   return docs (`count:[50,50]`), **including the confidential source `cockpit-mcp-telemetry`**, and the
   confidential doc IS reachable + cited. `filterAddOn` composes AND-wise *on top of* the header trim
   (header alone `[50,50]` → header + `groups eq confidential` `[24]`), i.e. it can only NARROW — never widen
   past the permission boundary. So per-user ACL = the header token's group membership, exactly as the
   direct-search path does today, but now with native agentic recall and a single head.

### Exact working KB-creation payload (SDK idiom — mirrors `app.knowledge.ingest_cockpit`, RULE #1)

Uses `azure.search.documents.indexes` models (`api_version=2026-05-01-preview`), non-destructively creating a
SEPARATE probe KS + KB over the **existing** index. Verified against the live SDK surface (not invented):

```python
from azure.search.documents.indexes.models import (
    SearchIndexKnowledgeSource, SearchIndexKnowledgeSourceParameters, SearchIndexFieldReference,
    KnowledgeBase, KnowledgeBaseAzureOpenAIModel, KnowledgeSourceReference,
    KnowledgeRetrievalMediumReasoningEffort, AzureOpenAIVectorizerParameters,
)
ks = SearchIndexKnowledgeSource(
    name="cockpit-si-probe-ks",
    search_index_parameters=SearchIndexKnowledgeSourceParameters(
        search_index_name="cockpit-docbundles-ks-index",              # the EXISTING ACL-stamped index
        source_data_fields=[SearchIndexFieldReference(name="blob_url"),
                            SearchIndexFieldReference(name="snippet")],
    ),
)
kb = KnowledgeBase(
    name="cockpit-si-probe-kb",
    knowledge_sources=[KnowledgeSourceReference(name="cockpit-si-probe-ks")],
    models=[KnowledgeBaseAzureOpenAIModel(azure_open_ai_parameters=AzureOpenAIVectorizerParameters(
        resource_url=<AZURE_AI_OPENAI_ENDPOINT>, deployment_name="gpt-5-mini", model_name="gpt-5-mini"))],
    output_mode="answerSynthesis",
    retrieval_reasoning_effort=KnowledgeRetrievalMediumReasoningEffort(),
)
client.create_or_update_knowledge_source(ks); client.create_or_update_knowledge_base(kb)
```

The app/dev identity (`DefaultAzureCredential`) **could** create + delete the probe KB/KS — **no BLOCKED**,
no extra role needed beyond what the dev already holds on the search service.

### The `filterAddOn` field + syntax that IS accepted (but is NOT the ACL lever — see fact 2)

- **api-version:** `2026-05-01-preview` (the `messages`-schema retrieve; the GA `2026-04-01` uses the older
  `intents` schema).
- **Request:** `POST {search}/knowledgebases/{kb}/retrieve?api-version=2026-05-01-preview`,
  `knowledgeSourceParams:[{ knowledgeSourceName, kind:"searchIndex", filterAddOn:"<OData>" }]`.
- **Syntax that was accepted + applied** (echoed into the subquery filter):
  `groups/any(g: search.in(g, '<comma-separated-object-ids>', ','))` — an OData ANY over the
  `Collection(Edm.String)` `groups` field. Confirmed correct; simply not sufficient for ACL here.

### The ACL lever that WORKS (use this for the next task)

Same request, **no** filterAddOn needed for ACL; add the header:
`x-ms-query-source-authorization: Bearer <the END USER's search-scoped token>` (service credential in the
`Authorization` header stays the APP identity, Search Index Data Reader). The user token carries the group
membership; the permission-enabled index trims to it. (In the non-interactive probe shell only the app/dev
token was available; it happens to be a member of the confidential group, so the probe confirmed the
confidential doc IS reachable via the header — a public-only User B token would trim it out, the same trim
the direct-search path relies on today.)

### Annotation → `{source, url, snippet}` mapping for the native searchIndex path

`response.output_text.annotation.added` won't fire on this raw retrieve; the citation carriers are:
- **`references[].docKey`** — a `<12hex>_<base64(blob_url)>N_pages_M` string. **`sourceData` is `null`** on
  the `answerSynthesis` output even with `source_data_fields` set (those fields feed the model, not the
  reference echo). Recover the source by **base64-decoding the middle segment**: e.g. docKey
  `24eef70b7e4d_aHR0cHM6…X19wYWdlLTEubWQ1_pages_0` → `https://…/cockpit-corpus/cockpit-mcp-telemetry-v1.2.0__page-1.md5`.
  → `source` = the blob filename; `url` = the (private) blob_url; `snippet` = the matching
  `response[0].content[0].text` chunk keyed by the answer's inline `[ref_id:N]` markers.
- **`response[0].content[0].text`** — the synthesized answer, grounded in the authorized docs, citing
  `[ref_id:N]` that cross-reference `references[].id`.

### Probe KB disposition

**Torn down** at the end (default). The probe is idempotent and re-creatable in seconds; `KEEP_PROBE_KB=1`
leaves it in place. Verified post-run: `cockpit-si-probe-kb`/`-ks` return 404, and production `cockpit-kb`
is untouched (still one source `cockpit-docbundles-ks`, `kind:azureBlob`).

### Implication for the next task (updated from STEP 0)

The **acl=True (cockpit)** path CAN move onto native agentic retrieval + a single head **if** the KB is
rebuilt on a **`searchIndex`** knowledge source over the ACL-stamped index, and the retrieve is called with
the **end-user's** search token as `x-ms-query-source-authorization` (service credential = app identity).
This replaces the direct-search-+-synthesize Plan B (a second, non-agentic retrieval head) with the native
agentic retrieve, while preserving the exact same per-user permission trim. **Do NOT** rely on `filterAddOn`
for the ACL — it's accepted but inert against a permission-enabled index. (The direct-search Plan B remains a
valid fallback and needs no index change; the index is already correctly armed.)

### Reproduce

```
cd apps/backend && uv run python -m eval.step0_searchindex_filter_probe   # KEEP_PROBE_KB=1 to keep the KB
```
Exit codes: `0` ✅ per-user ACL works on searchIndex via header / SKIP · `2` create/retrieve rejected ·
`3` inconclusive (confidential doc unreachable even with the header) · `4` BLOCKED (KB creation needs a
role the app lacks). Skips cleanly (SKIP:, rc 0) when infra/ACL-group env is absent.
