# Grounded Archetype Unification — Design

**Date:** 2026-07-01
**Status:** Proposed (brainstorming output; pending plan)
**Supersedes/extends:** `2026-07-01-grounded-obo-citations-design.md` (that slice shipped the two-path grounded bridge; this design *unifies* the two paths into one rich archetype).

---

## 1. Problem

After many phases the agent architecture drifted into an inconsistent shape ("caótico", per the owner). Concretely, today there are **4 domains** served **two different ways**, with the grounded path itself **forked in two**:

| Domain | `kind` | Live serving | Divergence |
|--------|--------|--------------|------------|
| helpdesk | workflow | `add_agent_framework_fastapi_endpoint` (AG-UI adapter) in `app/main.py` | — |
| cockpit | grounded (ACL) | router endpoint in `app/api/chat.py` → `stream_grounded_agui` (**acl=True**: direct-search + synthesize) | has `content` in citations |
| selfwiki | grounded | router endpoint in `app/api/chat.py` → `stream_grounded_agui` (**acl=False**: inline MCP `knowledge_base_retrieve` tool) | **no** `content` in citations |
| platform | tool | `add_agent_framework_fastapi_endpoint` (AG-UI adapter) in `app/main.py` | — |

Symptoms:

1. **Two serving mechanisms** (adapter in `main.py` vs router endpoints in `chat.py`), split across two files.
2. **Grounded is forked in two paths** inside `stream_grounded_agui` (`app/services/grounded.py`): cockpit uses direct-search-as-user + synthesize; selfwiki uses the inline MCP tool. → **content-on-click works only for cockpit**; selfwiki's native `url_citation`s carry no snippet.
3. **Backend has no domain registry** — the frontend has one (`apps/frontend/lib/domains.ts`), the backend wires each domain by hand.
4. **Redundant hosted twins** — the `*-hosted` twins existed as the keyless fallback for the service-principal 403 on raw inference; live-OBO now works for grounded, so the cockpit/selfwiki twins are dead weight.
5. **Dead-ish code coupled to eval — via TWO distinct surfaces** (verified):
   - **The agent builders + providers.** `build_cockpit_agent` (`app/agents/cockpit.py`) → `SecureAzureAISearchProvider` (`secure_search.py`); `build_selfwiki_agent` (`app/agents/selfwiki.py`) → `GroundedAzureAISearchProvider` (`grounded_search.py`). These are used by the live path **no longer**, but `eval/run_eval.py` still imports both builders as its `agent_factory` (`run_eval.py:35,37,239,250`). Removal chain: `run_eval` → builders → providers (must cut `run_eval` over **first**).
   - **The ACL trim primitives.** `eval/access_control_test.py`, `eval/red_team_test.py`, `eval/test_attribution.py` import `trim_agentic_content` / `authorized_components` / `_chunk_component` from `secure_search.py` (and `test_attribution.py` also `app.knowledge.acl_setup._component`). They do **not** touch the builders or the provider classes. This is a **separate** coupling that the archetype does not automatically replace.

## 2. Goal

**One rich grounded archetype** ("the Carlos head") that serves every grounded domain through a single code path, with domains reduced to **configuration data**. Keep the three properties the owner wants **together**:

1. **Native Microsoft retriever** (the managed Foundry IQ agentic retrieval — quality without us tuning it).
2. **Single head** (one grounded code path for all domains).
3. **Per-user ACL** (cockpit's confidential trimming — fail-closed).

The apparent conflict is **(1)↔(3)**: the native agentic `knowledge_base_retrieve` path was believed to never honor the per-user `x-ms-query-source-authorization` header (azure-sdk-for-python#44454). **STEP 0 + 0.5 resolved this (§4):** that gap is specific to `azureBlob`-backed KBs — a **`searchIndex`-backed KB honors the header**, so all three coexist by migrating the KB to a `searchIndex` source and trimming via the header. (`filterAddOn` is accepted but is *not* the ACL lever.) Plan B (direct-search) is retained as the fallback behind the same `retrieve()` seam.

Non-goals: merging knowledge bases (each domain keeps its **own isolated KB**); changing helpdesk's workflow internals or platform's tool internals; changing `self_hosted` behavior (byte-identical where the `deployment_mode` seam applies).

## 3. Architecture

### 3.1 The rich grounded archetype

A single assembly line with a clean contract. It receives `(question, user, domain_spec)` and returns the AG-UI SSE stream. Four stations:

1. **Identity (OBO)** — run as the signed-in user. The user is **captured in the endpoint and passed as an argument** — never read from the `current_user()` contextvar, which is lost inside the `StreamingResponse` async generator (verified; the bug that silently fell back to the app MI and 403'd). Preserved from the shipped design.
2. **Retrieve** — call the **native agentic retriever** over the domain's `searchIndex`-backed KB, service credential = app MI, with the **per-user `x-ms-query-source-authorization` header** for ACL domains (§4). Returns `[{index, source, url, snippet}]`. A domain without `permissionFilterOption` (no confidential content) returns docs with no header. **Fail-closed:** an ACL domain with no header returns zero docs; a source with no declared access does not enter the result.
3. **Synthesize** — answer from **only** the retrieved documents, with the citation directive (project rule #4: every grounded answer carries ≥1 source citation).
4. **Emit** — stream text deltas + a `sources` CUSTOM event `{index, source, url, content}` → clickable inline snippet for **every** grounded domain. Two invariants carried over verbatim from the shipped code (`grounded.py:239–243`) and must NOT regress in a reimplementation: `content` is the snippet **truncated to 800 chars**, and sources are **de-duplicated by URL** (the `seen` set).

**The seam that de-risks everything** is station 2, behind a single interface:

```python
# app/services/retrieval.py  (new)
async def retrieve(
    query: str, user, domain: DomainSpec, *, top: int = 8
) -> list[dict]:  # -> [{"index", "source", "url", "snippet"}]
    ...
```

**`retrieve()` owns BOTH retrieval identities internally** — this is deliberate, so the credential lifecycle does not leak into stations 1/3/4. Retrieval needs two distinct tokens (preserved from the shipped code, `grounded.py:216–224`): the **primary** search auth = the **app MI** (holds Search Index Data Reader; end users have no search RBAC), and the **per-user** trim = the user's token (the native filter's group values, or the `x-ms-query-source-authorization` header in Plan B). `retrieve()` acquires the app search token itself (via app credential) and derives the user dimension from the `user` argument — so the `(query, user, domain, *, top)` signature is sufficient and stations 1/3/4 stay ignorant of search credentials.

Stations 1/3/4 never change regardless of how `retrieve()` is implemented. If STEP 0 proves the native filter works, `retrieve()` calls the native retriever with the filter. If not, `retrieve()`'s body swaps to **Plan B** (§4.2) — **without touching stations 1/3/4**.

Error handling: a retrieval/synthesis failure surfaces as a clean `RunErrorEvent(message=str(exc), code=type(exc).__name__)` (no stack leak), mirroring `hosted.stream_agui`.

### 3.2 Backend domain registry + dispatch by `kind`

A backend registry mirroring `apps/frontend/lib/domains.ts`:

```python
# app/domains.py  (new)
@dataclass(frozen=True)
class DomainSpec:
    id: str
    kind: Literal["grounded", "workflow", "tool"]
    kb_name: str | None          # grounded only
    search_index: str | None     # grounded only
    acl_group_map: dict | None   # grounded: ACL is DATA (rule #6); None/empty → no-op filter
    instructions: str
    hosted_agent_name: str | None

DOMAINS: list[DomainSpec] = [ ... ]  # helpdesk, cockpit, selfwiki, platform
```

**One mount loop** iterates the registry; **one dispatcher by `kind`**:

- `grounded` → the rich archetype (§3.1). *(cockpit, selfwiki, future domains.)*
- `workflow` → the existing helpdesk handler (`WorkflowBuilder` triage→resolve→HITL — **internals unchanged**).
- `tool` → the existing platform handler (Microsoft MCP servers — **internals unchanged**).

**helpdesk and platform enter the registry** (as rows) but keep their own handlers. The unification is of **mounting/serving** (kills the `main.py`/`chat.py` split), **not** of their internals — they are genuinely different `kind`s and are not grounded. The registry becomes the single place that declares "these are the domains, and this is how each `kind` is served".

### 3.3 What the current code becomes

- `app/services/grounded.py` → the two-path `stream_grounded_agui` collapses to the single archetype (§3.1); the `acl` boolean and the `build_responses_kwargs` (MCP) vs `build_synthesis_kwargs` (direct) fork **go away** — both replaced by `retrieve()` + one synthesis path. `_async_credential(user)`, the app-vs-user token split, and the private-blob `content` inlining are **preserved** (they're correct and hard-won).
- `app/api/chat.py` grounded router endpoints → replaced by the registry mount loop; each grounded endpoint captures `current_user()` in the endpoint and calls the archetype.
- `app/main.py` → the workflow/tool mounts move under the same registry loop.

## 4. The retrieval reconciliation (STEP 0 — RESOLVED)

STEP 0 ran as two runnable `eval/` probes against live infra; full record in `docs/superpowers/plans/2026-07-01-grounded-archetype-unification-STEP0-findings.md`. Verdict: **all three (native retriever + single head + per-user ACL) ARE achievable — via the `x-ms-query-source-authorization` header over a `searchIndex`-backed KB.** The key discovery: the "agentic ignores ACL" blocker (#44454) was **specific to `azureBlob`-backed KBs**; a `searchIndex`-backed KB **honors the header**.

### 4.1 The mechanism (what `retrieve()`'s body does)

For a `searchIndex`-backed KB over an ACL-stamped index (`permissionFilterOption=enabled`, `permissionFilter=groupIds`, filterable `groups` field):

- **Service credential = app MI** (Search Index Data Reader) — always. End users have no search RBAC, so the user token is never the service credential.
- **Per-user ACL = the `x-ms-query-source-authorization: Bearer <end-user search token>` header** on the native agentic retrieve. The searchIndex retriever honors it: without it, `permissionFilterOption` returns **zero** candidates (fail-closed); with it, subqueries return the docs that user may read, including permission-gated ones. This is the **same header** the direct-search path uses today — now over the native agentic retriever (query planning, multi-subquery recall).
- **`filterAddOn` is NOT the ACL lever.** It is accepted on `searchIndex` sources and composes AND-wise (narrows only, never widens past the permission boundary), but with `permissionFilterOption` enabled it is inert as an access control — the header does the trimming. `filterAddOn` remains available for *optional* content narrowing, not ACL. (This corrected the design's original "pre-retrieval filter" hypothesis, which STEP 0 empirically refuted.)
- **Fail-closed by construction:** the retriever never sees nor reasons over unauthorized documents — the permission trim removes them before synthesis. This preserves the property the rejected "post-filter" approach violated (there the model reasons over confidential content, then hides the citation → prose leak).

**Prerequisite (new work):** the KB must be **migrated from `azureBlob` to `searchIndex`** over the existing ACL-stamped index (`cockpit-docbundles-ks-index`; already `groups`-stamped and queried by the current direct-search path). Verified live: creating a `searchIndex` KB over that index needs no extra role; the app/dev identity can create+delete it. `api-version 2026-05-01-preview`.

**Citations (native searchIndex path):** `references[].docKey` = `<12hex>_<base64(blob_url)>N_pages_M`; `sourceData` is `null` on the answer-synthesis path. Mapping: base64-decode the middle segment → `blob_url` → `source` = filename, `url` = (private) blob URL, `snippet` = the matching `response[0].content[0].text` chunk by `[ref_id:N]`. This parsing lives inside `retrieve()`; stations 3/4 still receive the uniform `[{index,source,url,snippet}]`.

### 4.2 Fallback (Plan B) — retained behind the same seam

If a domain's KB cannot be `searchIndex`-backed, `retrieve()`'s body falls back to **direct-search-as-user** (`_direct_search_authorized` — the proven header-trimmed `/docs/search`), optionally with our own lightweight query planning. Single head + ACL + content preserved; only the *managed* native agentic recall is lost for that domain. Same `retrieve()` interface, so §3's shape is unchanged either way. Plan B is the fallback, not the primary — the primary is §4.1.

## 5. Housekeeping

1. **Hosted twins:** retire the grounded twins (`/cockpit-hosted`, `/selfwiki-hosted`) — live-OBO grounded is proven. Keep `/helpdesk-hosted` (the workflow still 403s live via the app MI on raw inference). `/platform-hosted` stays (it is the D-packaging twin). The frontend Live/Hosted toggle disappears for grounded domains: drop `hostedAgentId` from the `cockpit` (`domains.ts:62`) and `selfwiki` (`domains.ts:78`) entries **and** update the adjacent comment blocks (`domains.ts:60–61,77`) that justify the twins as the "MI can invoke, live 403s" path — that justification is now stale for grounded (live-OBO works), so leaving the comments would contradict the removal.
2. **Eval coupling — the two surfaces are reconciled separately (§1.5):**
   - **Builders + providers (golden eval).** Cut `eval/run_eval.py`'s `agent_factory` over to the archetype's **`retrieve()`** (single source of truth — eval then exercises the production retrieval, not a parallel one). *Only after* that rewire, remove the now-unused chain in dependency order: `build_cockpit_agent` / `build_selfwiki_agent` first, then `SecureAzureAISearchProvider` / `GroundedAzureAISearchProvider`.
   - **Trim primitives (ACL/red-team/attribution tests).** These are a **separate decision**, not auto-removed. Default: **keep** `trim_agentic_content` / `authorized_components` / `_chunk_component` in `secure_search.py` — they test the ACL-trim invariants directly and are cheap to retain. If the archetype makes any of them genuinely unreachable, re-express the affected round-trip assertion against `retrieve()` in the same PR; do **not** delete a primitive while a test imports it.
   - **Plan B supersedes the currently-documented fallback.** `app/main.py:83` documents the retained builders as the *app-side-ACL-trim fallback while header-based trimming is verified*. This design **repurposes** that role: Plan B (§4.2) is `_direct_search_authorized` (direct-search-as-user), not the agent-framework provider trim. So the builders are being **deliberately retired**, and that `main.py` comment is removed — they are not merely "dead-ish".
3. **Bridges:** of the three (`stream_grounded_agui`, `stream_agui`, `stream_platform_agui`), the archetype absorbs the grounded one; the other two remain bound to their `kind` (workflow/tool).

## 6. Testing & rollout

Test convention (repo): runnable `def main() -> int` modules in `apps/backend/eval/`, no pytest, run with `uv run python -m eval.<name>` from `apps/backend/`.

1. **STEP 0** — native-retriever-accepts-filter probe (the gate, §4.2).
2. **Archetype ACL round-trip** — two users A vs B; A (in the confidential group) sees the confidential source, B does not. Assert on **cited source filenames**, not answer prose (a lesson from the shipped slice: B's prose can mention the topic without citing the confidential doc).
3. **E2E** — adapt the existing `e2e/cockpit-acl.spec.ts` browser A-vs-B test to the unified endpoint.
4. **Infra-free green** — `import app.main`, payload-shape tests, all pass without creds; infra-gated tests skip cleanly.

Rollout order: **migrate cockpit-kb to a `searchIndex` source** (§4.1 prerequisite) → **cockpit first** (the hard case — it has ACL) → **selfwiki** (same path; its index without `permissionFilterOption` returns docs with no header). helpdesk/platform enter the registry without touching their internals.

Constraints held throughout: keyless / `DefaultAzureCredential` + OBO (no API keys); ACL is **data**, not code (rule #6); `self_hosted` byte-identical where the `deployment_mode` seam applies; every grounded answer carries ≥1 citation (rule #4).

## 7. Risks

| Risk | Mitigation |
|------|------------|
| KB migration (blob→searchIndex) regresses recall/citations for cockpit | STEP 0.5 proved the searchIndex retrieve reaches + cites the confidential doc; validate the migrated production KB with the A-vs-B round-trip before cutover; keep the blob KB until green |
| Native searchIndex path returns 0 docs (header missing / index not permission-stamped) | Fail-closed is the safe failure; `retrieve()` asserts the header is attached for ACL domains; the index is already `permissionFilterOption=enabled` + `groups`-stamped (verified) |
| `docKey` citation parsing brittle (base64 decode, `sourceData` null) | Parsing isolated inside `retrieve()`; covered by the shape test; stations 3/4 see only the uniform `[{index,source,url,snippet}]` |
| Eval refactor changes what's measured | Point eval at `retrieve()` so it measures the production path; keep the golden set unchanged |
| `deployment_mode` regression | Gate any behavior change behind `settings.deployment_mode`; `self_hosted` stays byte-identical |

## 8. Resolved / open questions

- **RESOLVED (STEP 0 + 0.5):** the three coexist via the `x-ms-query-source-authorization` header over a `searchIndex`-backed KB; `filterAddOn` is not the ACL lever; api-version `2026-05-01-preview`; KB migration needs no extra role. See the findings file.
- **Open:** whether `/platform-hosted` remains the only tool twin or also gains a live path later (out of scope here).
