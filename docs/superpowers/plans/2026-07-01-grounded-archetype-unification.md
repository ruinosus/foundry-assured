# Grounded Archetype Unification — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the two forked grounded paths (cockpit direct-search+ACL vs selfwiki inline-MCP) into ONE rich grounded archetype fronted by a single `retrieve()` seam, driven by a backend `DomainSpec` registry with dispatch-by-`kind`, keeping the native Microsoft retriever + single head + per-user ACL together.

**Architecture:** A single `retrieve(query, user, domain) -> [{index,source,url,snippet}]` seam owns both retrieval identities (app-MI service credential + per-user ACL header) and hides the retrieval mechanism. STEP 0 + 0.5 RESOLVED the mechanism: **native agentic retrieve over a `searchIndex`-backed KB, per-user ACL via the `x-ms-query-source-authorization` header** (which searchIndex KBs honor — the #44454 gap was blob-specific); direct-search is the fallback behind the same seam. One archetype (`stream_grounded`) runs the 4 stations (OBO → retrieve → synthesize → emit) for every grounded domain. A backend `DomainSpec` registry mirrors `apps/frontend/lib/domains.ts`; one mount loop dispatches by `kind` (grounded → archetype, workflow → helpdesk, tool → platform). A prerequisite migrates `cockpit-kb` from `azureBlob` to `searchIndex`.

**Tech Stack:** Python 3.12, `azure-ai-projects` (Responses API, `.aio`), `azure-identity` OBO, FastAPI, `agent-framework-ag-ui`, `httpx`. Tests: runnable `def main()->int` modules in `apps/backend/eval/` (NO pytest), run `uv run python -m eval.<name>` from `apps/backend/`.

**Spec:** `docs/superpowers/specs/2026-07-01-grounded-archetype-unification-design.md` — read it first.

---

## Ground rules (apply to EVERY task)

- **Rule #1 — do not invent SDK signatures.** The native-retriever filter shape + its `api-version` are UNVERIFIED. They are discovered by STEP 0 (Chunk 1) and only then written into code (Chunk 2). Until then, any native-filter call is provisional; leave `# TODO: verify signature` if unconfirmed.
- **Rule #2 — keyless.** `DefaultAzureCredential` / OBO only. No API keys.
- **Rule #4 — every grounded answer carries ≥1 citation.**
- **Rule #6 — ACL is DATA, fail-closed.** Groups come from the source/config, never classification logic in code. A source with no declared access does not enter results.
- **`self_hosted` byte-identical** where the `deployment_mode` seam applies: any behavior change is gated behind `settings.deployment_mode`. The `_domain_deps`/`_hosted_deps` gate stays as-is.
- **Preserve from `grounded.py` (hard-won, do NOT regress):** user captured in the endpoint via `current_user()` and passed as an arg (the contextvar is lost in the generator); the two-identity split (primary search = app MI with Search Index Data Reader, per-user trim = user token); `content` = snippet truncated to **800 chars**; sources **deduped by URL**.
- **Commit after every task.** Conventional commits. Branch: `feature/grounded-obo-citations`.

## File Structure

| File | Responsibility | Action |
|------|----------------|--------|
| `apps/backend/eval/step0_native_filter_probe.py` | STEP-0 gate: does the native retriever trim by a caller-supplied group filter? Capture shape + api-version. | Create |
| `apps/backend/app/services/retrieval.py` | The `retrieve()` seam. Owns both identities. Primary: native agentic retrieve + ACL header over a searchIndex KB (STEP 0.5). Fallback: `_direct_search_authorized`. Returns `[{index,source,url,snippet}]`. | Create |
| `apps/backend/app/knowledge/ingest_cockpit.py` | Migrate `cockpit-kb` from an `azureBlob` to a `searchIndex` knowledge source over the existing ACL-stamped `cockpit-docbundles-ks-index` (Task 2b — unblocks the native ACL header). | Modify |
| `apps/backend/app/services/grounded.py` | Collapses to the single archetype `stream_grounded(body, domain, user)` (4 stations) using `retrieve()`. Drop the `acl` fork + `build_responses_kwargs`. Keep `_async_credential`, `build_synthesis_kwargs`, emit invariants. | Modify |
| `apps/backend/app/domains.py` | Backend `DomainSpec` registry (mirrors `domains.ts`) + `mount_domains(app)` loop dispatching by `kind`. **Owns `_domain_deps`** (moved from `main.py`) to break the `main↔domains` cycle and de-dupe `chat.py::_hosted_deps`. | Create |
| `apps/backend/app/api/chat.py` | Remove the grounded `/cockpit` + `/selfwiki` router endpoints (moved into the mount loop) and the two redundant grounded hosted twins. Drop the local `_hosted_deps`; import `_domain_deps` from `app.domains`. | Modify |
| `apps/backend/app/main.py` | Replace the hand-wired helpdesk/platform mounts + the grounded comment block with `mount_domains(app)`. Import `_domain_deps` from `app.domains`. | Modify |
| `apps/backend/eval/grounded_payload_test.py` | Rewrite: drop `build_responses_kwargs`/`CITATION_DIRECTIVE` assertions; keep `build_synthesis_kwargs`. | Modify |
| `apps/backend/eval/grounded_acl_roundtrip_test.py` | Retire (imports removed `GroundedDomain`; coverage moved to the new round-trip tests). | Delete |
| `apps/backend/eval/run_eval.py` | Rewire `agent_factory` off `build_*_agent` onto `retrieve()`. | Modify |
| `apps/backend/app/agents/{cockpit,selfwiki,secure_search,grounded_search}.py` | Remove the builders + provider classes AFTER run_eval is rewired. Keep the trim primitives in `secure_search.py` (tests import them). | Modify/Delete |
| `apps/frontend/lib/domains.ts` | Drop `hostedAgentId` from cockpit+selfwiki and update the now-stale twin-justification comments. | Modify |
| `apps/backend/eval/grounded_archetype_roundtrip_test.py` | A-vs-B ACL round-trip over the unified archetype's `retrieve()`. | Create |
| `e2e/cockpit-acl.spec.ts` | Adapt the browser A-vs-B assertion to the unified endpoint. | Modify |

**Rollout order:** cockpit first (has ACL — the hard case), then selfwiki. helpdesk/platform enter the registry without touching internals.

---

## Chunk 1: STEP 0 — the retrieval gate ✅ RESOLVED

**This gate precedes everything.** It ran as TWO probes (Task 1 = `azureBlob` filter probe; Task 1b/STEP 0.5 = `searchIndex` re-probe), both committed. **Outcome:** the caller-supplied `filterAddOn` is NOT the ACL lever (inert under `permissionFilterOption`); instead the **native agentic retrieve over a `searchIndex`-backed KB honors the `x-ms-query-source-authorization` header** → all three (native + single head + ACL) coexist. `retrieve()`'s primary body is the native-header path; direct-search is the fallback. Full record: `docs/superpowers/plans/2026-07-01-grounded-archetype-unification-STEP0-findings.md`. Tasks 1 and 1b below are **DONE** (kept for provenance); proceed to Chunk 2 + the new Task 2b (KB migration).

### Task 1: STEP-0 native-filter probe

**Files:**
- Create: `apps/backend/eval/step0_native_filter_probe.py`
- Reference: `apps/backend/eval/step0_grounded_citations_spike.py` (the existing spike — same skip/print/dump idiom), `apps/backend/eval/grounded_acl_roundtrip_test.py` (the ROPC two-user token helper).

- [ ] **Step 1: Write the probe as a runnable throwaway (not a product test)**

Model it on `step0_grounded_citations_spike.py`. It must, against live infra, using **two test users** (A in the `confidential` group, B public-only — reuse `COCKPIT_TEST_USER_A/B`, `COCKPIT_TEST_PASSWORD`, `COCKPIT_CONFIDENTIAL_SOURCE` from `grounded_acl_roundtrip_test.py`):

1. Call the **native Foundry IQ retriever** (`knowledge_base_retrieve` MCP tool, or its direct retrieve endpoint) with a **caller-supplied group filter** built from each user's authorized groups — NOT the `x-ms-query-source-authorization` header (that path is known-inert).
2. Assert the trim: **A's** result contains the confidential source, **B's** does not.
3. Probe the **`api-version`** independently: try the pinned `2026-05-01-preview` first; if the filter param is rejected, retry known newer preview versions and RECORD which (if any) accepts it. Do not assume the pinned one.
4. `_dump()` the exact request shape that worked (tool/retrieve payload, the filter field name + syntax) and the response, so Chunk 2 is authored from captured fact, not a guess.

Skip cleanly (`return 0`, print `SKIP:`) when infra/test-user env is absent, exactly like the existing spike.

- [ ] **Step 2: Run it against live infra**

Run: `cd apps/backend && uv run python -m eval.step0_native_filter_probe`
Expected (infra present): a clear verdict —
- ✅ "native retriever trims by filter" + the captured shape + the working api-version, OR
- ❌ "filter ignored / rejected on all probed versions" + the errors seen.

- [ ] **Step 3: Record the outcome in the plan's findings file**

Create `docs/superpowers/plans/2026-07-01-grounded-archetype-unification-STEP0-findings.md` capturing: verdict, the exact filter field name + syntax (if ✅), the api-version, and the annotation→`{source,url,snippet}` mapping for the native path. This file is the input to Task 2. (Note: this is a NEW file — do not overwrite the pre-existing `2026-07-01-grounded-obo-citations-STEP0-findings.md` from the prior shipped slice; different name, different scope.)

- [ ] **Step 4: Commit**

```bash
git add apps/backend/eval/step0_native_filter_probe.py docs/superpowers/plans/2026-07-01-grounded-archetype-unification-STEP0-findings.md
git commit -m "test(step0): probe native-retriever group-filter trim + api-version (unification gate)"
```

**Gate decision (RESOLVED — see the banner above):** Task 2's body = **native agentic retrieve + ACL header over a searchIndex KB** (NOT `filterAddOn`, which STEP 0.5 proved inert as an ACL lever); `_direct_search_authorized` is the fallback behind the same interface. Everything downstream is identical either way.

---

## Chunk 2: the `retrieve()` seam

### Task 2: `retrieve()` — the single retrieval interface owning both identities

**Files:**
- Create: `apps/backend/app/services/retrieval.py`
- Reference: `apps/backend/app/services/grounded.py:141-177` (`_direct_search_authorized`), `:33` (`_SEARCH_SCOPE`, `_KB_API`), the STEP-0 findings file.
- Test: `apps/backend/eval/retrieval_shape_test.py` (create)

- [ ] **Step 1: Write the failing shape test (infra-free)**

`retrieval_shape_test.py` asserts the CONTRACT without hitting infra: build a `DomainSpec` (see Task 5) with an empty `acl_group_map`, monkeypatch the underlying search call to return two fixture rows (one duplicate URL), call `retrieve()`, and assert the output is exactly `[{index,source,url,snippet}]`, **1-based `index`**, **deduped by URL**, and **`snippet` present**. No credential is acquired when the search call is patched.

```python
# eval/retrieval_shape_test.py (sketch)
async def _run() -> int:
    from app.services import retrieval
    rows = [ {"blob_url": "https://x/a.md", "snippet": "S1"},
             {"blob_url": "https://x/a.md", "snippet": "dup"},
             {"blob_url": "https://x/b.md", "snippet": "S2"} ]
    # patch the low-level fetch retrieve() delegates to, so no network/creds:
    retrieval._raw_search = lambda *a, **k: rows            # name per your impl
    docs = await retrieval.retrieve("q", user=None, domain=_fake_domain())
    assert [d["index"] for d in docs] == [1, 2], docs       # deduped to 2
    assert docs[0] == {"index":1,"source":"a.md","url":"https://x/a.md","snippet":"S1"}
    print("✅ retrieve() contract holds"); return 0
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.retrieval_shape_test`
Expected: FAIL (`ModuleNotFoundError: app.services.retrieval` or `AttributeError`).

- [ ] **Step 3: Implement `retrieve()` — STEP-0 outcome: native agentic retrieve + header over a `searchIndex` KB**

STEP 0 + 0.5 RESOLVED the gate (findings: `docs/superpowers/plans/2026-07-01-grounded-archetype-unification-STEP0-findings.md`, and the runnable probe `eval/step0_searchindex_filter_probe.py` — READ BOTH; author this body from their captured shape, not from guesses; rule #1). Verdict: **the native agentic retriever over a `searchIndex`-backed KB honors the `x-ms-query-source-authorization` header** → primary path. `filterAddOn` is NOT the ACL lever. The signature + identity-ownership are fixed:

```python
# app/services/retrieval.py
"""The single grounded retrieval seam. Owns BOTH retrieval identities so the archetype
(stations 1/3/4) never touches search credentials:
  - service credential = the APP managed identity (Search Index Data Reader). End users have no
    search RBAC, so the user token is NEVER the service credential.
  - per-user ACL       = the x-ms-query-source-authorization: Bearer <end-user search token> header.
    The native agentic retrieve over a searchIndex-backed KB HONORS it (STEP 0.5). Without it, an
    ACL index (permissionFilterOption=enabled) returns ZERO docs — fail-closed (rule #6).
Returns authorized docs as [{index, source, url, snippet}] — deduped by URL, 1-based index."""
from __future__ import annotations

_SEARCH_SCOPE = "https://search.azure.com/.default"
_KB_API = "2026-05-01-preview"   # verified in STEP 0.5

async def retrieve(query: str, user, domain, *, top: int = 8) -> list[dict]:
    from azure.identity.aio import DefaultAzureCredential as _AppCredential
    app_cred = _AppCredential()
    try:
        primary = (await app_cred.get_token(_SEARCH_SCOPE)).token   # app MI (service credential)
        user_token = await _user_search_token(user)                 # OBO, or None (dev/no-auth/public domain)
        if domain.kb_name:                                          # PRIMARY: native agentic retrieve
            rows = await _native_retrieve(domain, query, primary, user_token, top=top)
        else:                                                        # FALLBACK (Plan B): direct-search-as-user
            rows = await _direct_search_authorized(domain, query, primary, user_token, top=top)
        return _project(rows)   # -> [{index,source,url,snippet}], deduped by URL, 1-based
    finally:
        import contextlib
        with contextlib.suppress(Exception):
            await app_cred.close()
```

`_native_retrieve(domain, query, primary, user_token, top)` calls the KB retrieve on `domain.kb_name` over `domain.search_endpoint` at `_KB_API`, service auth = `primary`, and attaches `x-ms-query-source-authorization: Bearer {user_token}` **when `user_token` is not None** (ACL domains). Parse the response per the findings: `references[].docKey` → base64-decode the middle `<base64(blob_url)>` segment → `blob_url`; `source` = filename, `url` = blob_url, `snippet` = the `response[0].content[0].text` chunk matched by `[ref_id:N]`. Copy the exact request/parse shape from `eval/step0_searchindex_filter_probe.py` — do NOT re-derive it.

`_project()` centralizes the dedup+index invariant (moved out of `stream_grounded_agui`). `_user_search_token(user)` mirrors the OBO logic in `grounded._async_credential` (returns `None` when `not settings.auth_enabled or user is None`).

**Fallback (Plan B) reads endpoint + index off the domain.** `_direct_search_authorized` dereferences `domain.search_endpoint` (grounded.py:158) and `domain.search_index`. Move it into `retrieval.py`; the `DomainSpec` carries `search_endpoint` (from `cfg.azure_search_endpoint`) + `search_index` (Task 5). The shape test's `_fake_domain()` is a `DomainSpec` (or stub exposing `.kb_name`/`.search_endpoint`/`.search_index`); patch `_native_retrieve`'s low-level fetch so no network/creds. **Note:** the primary path keys on `domain.kb_name` being set — cockpit/selfwiki both have one; Plan B is only reached for a (hypothetical) KB-less grounded domain.

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.retrieval_shape_test`
Expected: PASS (`✅ retrieve() contract holds`).

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/services/retrieval.py apps/backend/eval/retrieval_shape_test.py
git commit -m "feat(retrieval): single retrieve() seam — native agentic retrieve + ACL header over searchIndex KB"
```

### Task 2b: Migrate `cockpit-kb` to a `searchIndex` knowledge source (infra prerequisite)

**Why:** `retrieve()`'s native path (Task 2) only honors the ACL header when the KB's knowledge source is `kind: searchIndex` (STEP 0.5). The production `cockpit-kb` is `azureBlob` today. This task makes the searchIndex-backed KB real, non-destructively.

**Files:**
- Modify: `apps/backend/app/knowledge/ingest_cockpit.py` (and/or `ingest.py` / `acl_setup.py` — wherever the cockpit KB + knowledge source are provisioned).
- Reference: `apps/backend/eval/step0_searchindex_filter_probe.py` (the verified `SearchIndexKnowledgeSource` / `SearchIndexKnowledgeSourceParameters` creation over `cockpit-docbundles-ks-index`), the STEP-0 findings file.

- [ ] **Step 1: Locate the current cockpit KB provisioning**

Read `ingest_cockpit.py`/`ingest.py` to find where `cockpit-kb` + its `azureBlob` knowledge source (`cockpit-docbundles-ks`) are created. Note: `cockpit-docbundles-ks-index` already exists, ACL-stamped (`groups` filterable, `permissionFilterOption=enabled`) — the index is NOT rebuilt, only the KB's knowledge source changes.

- [ ] **Step 2: Add/point the KB at a `searchIndex` knowledge source**

Update the provisioning to create the `cockpit-kb` knowledge source as `searchIndex` over the existing `cockpit-docbundles-ks-index` (mirror the exact SDK model calls proven in `step0_searchindex_filter_probe.py`). **Non-destructive cutover:** create the searchIndex-backed source alongside, verify (Step 3), then switch `cockpit-kb` to it. Keep the blob source until the A-vs-B check is green (spec §7 risk).

- [ ] **Step 3: Verify the production KB with the A-vs-B probe**

Run: `cd apps/backend && uv run python -m eval.step0_searchindex_filter_probe` (repointed at the real `cockpit-kb`, or a thin variant that targets `cfg.cockpit_search_knowledge_base`).
Expected: User A (confidential group) retrieves + cites `COCKPIT_CONFIDENTIAL_SOURCE`; User B does not. If red → do NOT cut over; keep the blob source and report.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/app/knowledge/ingest_cockpit.py
git commit -m "feat(kb): cockpit-kb on a searchIndex knowledge source (unlocks native agentic retrieve + ACL header)"
```

### Task 3: `retrieve()` ACL parity with the shipped path (infra-gated)

**Files:**
- Create: `apps/backend/eval/retrieval_acl_parity_test.py`
- Reference: `apps/backend/eval/grounded_acl_roundtrip_test.py` (the exact A-vs-B ROPC harness).

- [ ] **Step 1: Write the parity test**

Clone `grounded_acl_roundtrip_test.py` but call `retrieval.retrieve()` (user A, user B) instead of `_direct_search_authorized` directly. Assert **A gets `COCKPIT_CONFIDENTIAL_SOURCE`, B does not** (same fail-closed assertion; assert on `source` filenames). Skip cleanly without the test-user env.

- [ ] **Step 2: Run it**

Run: `cd apps/backend && uv run python -m eval.retrieval_acl_parity_test`
Expected (infra present): `✅ PASS: A retrieves the confidential doc, B does not`. (Absent infra: clean SKIP.)

- [ ] **Step 3: Commit**

```bash
git add apps/backend/eval/retrieval_acl_parity_test.py
git commit -m "test(retrieval): A-vs-B ACL parity over retrieve() (fail-closed)"
```

---

## Chunk 3: the unified archetype

### Task 4: Collapse `stream_grounded_agui` into the single archetype

**Files:**
- Modify: `apps/backend/app/services/grounded.py`
- Rewrite: `apps/backend/eval/grounded_payload_test.py` — **it will break** (it imports `CITATION_DIRECTIVE`, `build_responses_kwargs`, and the `acl=True/False` `GroundedDomain` forks — all deleted in Step 3). It does NOT stay green unchanged.
- Test: `apps/backend/eval/archetype_emit_test.py` (create)

- [ ] **Step 1: Write a failing emit-invariants test (infra-free)**

`archetype_emit_test.py`: monkeypatch `retrieval.retrieve` to return 3 fixture docs (one snippet >800 chars, one duplicate URL already deduped upstream) and patch the Responses stream to yield two text deltas. Drive `stream_grounded(body, domain, user=None)`, collect the encoded AG-UI events, and assert: a `sources` CustomEvent fires with `content` truncated to **800 chars**, `{index,source,url,content}` keys, and text deltas passed through. This locks the two carried-over invariants.

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.archetype_emit_test`
Expected: FAIL (`stream_grounded` doesn't exist yet).

- [ ] **Step 3: Refactor `grounded.py` to the archetype**

- Rename/replace `stream_grounded_agui` with `stream_grounded(body, domain: DomainSpec, user=None)`. Keep the AG-UI event scaffolding (RunStarted → TextMessageStart → deltas → TextMessageEnd → `sources` CustomEvent → RunFinished; clean `RunErrorEvent` on except).
- **Station 2 becomes one line:** `docs = await retrieve(user_text, user, domain)`. DELETE the `if domain.acl:` fork, `build_responses_kwargs`, the inline MCP tool block, the annotation-collection branch, and the app/user token acquisition (now inside `retrieve()`).
- **Station 3:** always `build_synthesis_kwargs(user_text, domain, docs, model=...)` — synthesize from the retrieved docs only (rule #4). Keep `build_synthesis_kwargs` + `SYNTHESIS_DIRECTIVE`.
- **Station 4:** `sources = [{"index": d["index"], "source": d["source"], "url": d["url"], "content": (d.get("snippet") or "")[:800]} for d in docs]` — the 800-char cap preserved; dedupe already done in `retrieve()`.
- Keep `_async_credential(user)` (OBO for the *inference* call — station 1). Remove `_source_from_annotation` and `CITATION_DIRECTIVE` (MCP-only, now dead).
- **`GroundedDomain` is removed** (superseded by `DomainSpec`, Task 5). Its importers are handled deterministically: `grounded_payload_test.py` is rewritten in this task (Step 4); `grounded_acl_roundtrip_test.py` is retired in Task 8 (its coverage is replaced by `retrieval_acl_parity_test` Task 3 + `grounded_archetype_roundtrip_test` Task 10). Run `grep -rn "GroundedDomain\|_direct_search_authorized" eval app` and confirm the only remaining references are the ones this plan explicitly repoints — nothing else may import them after Task 8.
- **`_direct_search_authorized` moves to `retrieval.py`** (Task 2) since it's now Plan B's engine, not a `grounded.py` internal.

- [ ] **Step 4: Rewrite `grounded_payload_test.py` for the collapsed path**

Drop the `build_responses_kwargs`/`CITATION_DIRECTIVE`/`acl=` assertions (those symbols no longer exist). Keep only the `build_synthesis_kwargs` assertions (docs are the ONLY context; empty-docs branch). Update its imports to the surviving symbols. If `GroundedDomain` is being replaced by `DomainSpec` (Step 3), repoint the test's construction accordingly.

- [ ] **Step 5: Run both tests**

Run: `cd apps/backend && uv run python -m eval.archetype_emit_test && uv run python -m eval.grounded_payload_test`
Expected: both PASS. Also `uv run python -c "import app.main"` still imports.

- [ ] **Step 6: Commit**

```bash
git add apps/backend/app/services/grounded.py apps/backend/eval/archetype_emit_test.py apps/backend/eval/grounded_payload_test.py
git commit -m "refactor(grounded): collapse acl/mcp fork into one archetype over retrieve()"
```

---

## Chunk 4: the backend registry + dispatch

### Task 5: `DomainSpec` registry + `mount_domains(app)` dispatch by kind

**Files:**
- Create: `apps/backend/app/domains.py`
- Reference: `apps/frontend/lib/domains.ts` (mirror), `apps/backend/app/main.py:54-97`, `apps/backend/app/api/chat.py:12-19` (the `_domain_deps` gate), `apps/backend/app/agents/prompts.py` (COCKPIT_INSTRUCTIONS/SELFWIKI_INSTRUCTIONS).
- Test: `apps/backend/eval/domain_registry_test.py` (create)

- [ ] **Step 1: Write a failing registry test (infra-free)**

Assert `DOMAINS` has the 4 ids (`helpdesk,cockpit,selfwiki,platform`) with the right `kind` map (`workflow,grounded,grounded,tool`); grounded specs carry `kb_name`+`instructions`; and that `mount_domains(fake_app)` registers a POST route per grounded domain and calls the adapter for workflow/tool (use a fake app recording `add_api_route`/mount calls). Verify grounded endpoints are gated by `_domain_deps(id)`.

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.domain_registry_test`
Expected: FAIL (`app.domains` missing).

- [ ] **Step 3: Implement the registry + mount loop**

```python
# app/domains.py
from dataclasses import dataclass
from typing import Literal

@dataclass(frozen=True)
class DomainSpec:
    id: str
    kind: Literal["grounded", "workflow", "tool"]
    instructions: str = ""
    kb_name: str | None = None
    search_index: str | None = None
    search_endpoint: str = ""           # REQUIRED for grounded — Plan B's _direct_search_authorized reads it
    acl_group_map: dict | None = None   # ACL is DATA (rule #6); name→objectID; None/empty → no-op filter
    hosted_agent_name: str | None = None

def _domains() -> list[DomainSpec]:
    from app.agents.prompts import COCKPIT_INSTRUCTIONS, SELFWIKI_INSTRUCTIONS
    from app.core.tenant import tenant_config
    cfg = tenant_config()
    return [
        DomainSpec("helpdesk", "workflow", hosted_agent_name=cfg.hosted_agent_name),
        DomainSpec("cockpit", "grounded", COCKPIT_INSTRUCTIONS,
                   kb_name=cfg.cockpit_search_knowledge_base, search_index=cfg.cockpit_search_index,
                   search_endpoint=cfg.azure_search_endpoint,
                   acl_group_map=cfg.acl_group_map),   # the PARSED PROPERTY (dict name→objectID), NOT the raw str
        DomainSpec("selfwiki", "grounded", SELFWIKI_INSTRUCTIONS,
                   kb_name=cfg.selfwiki_search_knowledge_base, search_index=cfg.selfwiki_search_index,
                   search_endpoint=cfg.azure_search_endpoint),   # selfwiki: no acl_group_map → no-op filter
        DomainSpec("platform", "tool"),
    ]

def mount_domains(app) -> None:
    """One loop, dispatch by kind. self_hosted byte-identical: the gate is _domain_deps (shared-mode
    only adds the entitlement dep)."""
    for d in _domains():
        if d.kind == "grounded":
            _mount_grounded(app, d)
        elif d.kind == "workflow":
            _mount_helpdesk(app, d)      # existing add_agent_framework_fastapi_endpoint logic
        elif d.kind == "tool":
            _mount_platform(app, d)      # existing platform_agent_proxy logic
```

**Circular-import resolution (firm):** `_domain_deps` **moves into `app/domains.py`** (it belongs with the mount loop). `app/main.py` imports it from `app.domains` (not the reverse), and `app/api/chat.py` drops its duplicate `_hosted_deps` and imports the same `_domain_deps` from `app.domains`. This removes the `main ↔ domains` cycle and de-duplicates the gate. `_domains()` reads `tenant_config()` **lazily inside the function** (not at import), so importing `app.domains` has no import-time side effects.

**`acl_group_map` semantics (rule #6, fail-closed):** `cfg.acl_group_map` is the property (`tenant.py:84`) returning **group NAME → object-ID** — the SOURCE-side declaration of which groups may read, carried by `DomainSpec` as DATA. The native searchIndex path does per-user ACL via the **header token's group membership**, trimmed server-side — NOT via a caller-computed group filter (STEP 0.5 proved `filterAddOn` inert as an ACL lever). The map is consumed by the ingest/ACL-stamp (`acl_setup.py`) and by Plan B's direct-search; `retrieve()`/`_native_retrieve` do not compute a group intersection.

`_mount_grounded` registers a POST `/{d.id}` that captures `current_user()` in the endpoint and streams the archetype:

```python
def _mount_grounded(app, d: DomainSpec) -> None:
    from fastapi import Request
    from fastapi.responses import StreamingResponse
    from app.core.auth import current_user
    from app.services.grounded import stream_grounded
    async def endpoint(request: Request):
        return StreamingResponse(
            stream_grounded(await request.json(), d, current_user()),  # capture user HERE
            media_type="text/event-stream")
    app.add_api_route(f"/{d.id}", endpoint, methods=["POST"], dependencies=_domain_deps(d.id))
```

**Config fields already exist — do NOT add duplicates.** Verify (don't re-add): `cockpit_acl_group_map` (`tenant.py:55,119`, raw comma-str; consume via the `acl_group_map` property `:84`), `selfwiki_search_index` (`:51,117`, already defaults `selfwiki-docbundles-ks-index`), `hosted_agent_name` (`:69,127`), `azure_search_endpoint`. The native-header path needs no new filter field (STEP 0.5 identified none); `search_endpoint` on `DomainSpec` is added in Task 5 for Plan B.

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.domain_registry_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/domains.py apps/backend/app/core/tenant.py apps/backend/eval/domain_registry_test.py
git commit -m "feat(domains): backend DomainSpec registry + mount_domains dispatch by kind"
```

### Task 6: Wire `main.py`/`chat.py` to the mount loop

**Files:**
- Modify: `apps/backend/app/main.py`, `apps/backend/app/api/chat.py`
- Test: `apps/backend/eval/domains_api_test.py` (existing — the endpoint inventory; keep green)

- [ ] **Step 1: Check the route-inventory expectation**

Run: `cd apps/backend && uv run python -m eval.domains_api_test` (note current pass/fail + what routes it expects).

- [ ] **Step 2: Replace the hand-wiring in `main.py`**

Delete the explicit helpdesk `add_agent_framework_fastapi_endpoint` block (66-76), the grounded comment block (78-85), and the platform block (91-97). Replace with `mount_domains(app)` after `app.include_router(api_router)`. Move `_mount_helpdesk`/`_mount_platform` bodies (the existing `OrderedAgentFrameworkWorkflow` + `platform_agent_proxy` logic, incl. the `_knowledge_configured()`/`platform_configured()` guards) into `app/domains.py` so `main.py` stays wiring-only.

- [ ] **Step 3: Remove the grounded router endpoints from `chat.py`**

Delete `/cockpit` (22-45) and `/selfwiki` (48-67) — now mounted by the loop. Keep `/helpdesk-hosted` and `/platform-hosted`. (Grounded twins handled in Task 8.)

- [ ] **Step 4: Verify boot + route inventory**

Run: `cd apps/backend && uv run python -c "import app.main" && uv run python -m eval.domains_api_test`
Expected: imports clean; `/helpdesk`, `/cockpit`, `/selfwiki`, `/platform` all registered (POST); inventory test green (update its expectation if it enumerated the old router paths).

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/main.py apps/backend/app/api/chat.py apps/backend/app/domains.py
git commit -m "refactor(mounting): main.py/chat.py serve grounded via mount_domains (kills the 2-file split)"
```

---

## Chunk 5: housekeeping

### Task 7: Rewire `run_eval.py` off the builders onto `retrieve()`

**Files:**
- Modify: `apps/backend/eval/run_eval.py:35,37,239,250`
- Reference: `apps/backend/app/services/retrieval.py`

- [ ] **Step 1: Inspect the exact factory protocol**

The harness (`run_eval.py:300`) does `async with agent_factory() as agent:` then `_agent_answer(agent, q)` calls `(await agent.run(query)).text` (`:165-174`). So the replacement is NOT a "returns answer dict" helper — it must be an **async context manager** yielding an object with an `async run(query) -> obj_with_.text`. The cockpit/selfwiki golden evaluators score `cites_source` on the answer TEXT (`:87`), so the synthesized answer must carry the citations inline.

- [ ] **Step 2: Replace the factory with a retrieve()-backed adapter**

Add a small adapter that satisfies that protocol, sourcing from `retrieve()` + one synthesis call:

```python
# in run_eval.py (or a tiny eval/_retrieve_agent.py)
class _RetrieveAgent:
    def __init__(self, domain): self._d = domain
    async def __aenter__(self): return self
    async def __aexit__(self, *exc): return False
    async def run(self, query: str):
        from app.services.retrieval import retrieve
        from app.services.grounded import build_synthesis_kwargs
        docs = await retrieve(query, user=None, domain=self._d)     # eval runs as the app identity
        kwargs = build_synthesis_kwargs(query, self._d, docs, model=tenant_config().foundry_model)
        # non-streaming synthesis; return an object exposing .text (mirror _agent_answer's expectation)
        text = await _synthesize_text(kwargs)                       # helper: responses.create(stream=False).output_text
        return type("R", (), {"text": text})()
```

Set `agent_factory = lambda: _RetrieveAgent(_spec_for(domain))` where `_spec_for` builds the `DomainSpec` (reuse `app.domains._domains()`). Remove the `from app.agents.cockpit/selfwiki import build_*_agent` imports (`:35,37`). Leave the `build_concierge_agent` branch (`:257`) untouched — helpdesk is not grounded.

- [ ] **Step 3: Run the golden eval (infra-gated)**

Run: `cd apps/backend && uv run python -m eval.run_eval` (or its documented invocation).
Expected: runs against `retrieve()`; groundedness/rubric scores comparable to before. Clean SKIP without infra.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/eval/run_eval.py
git commit -m "refactor(eval): golden harness scores the production retrieve() path, not the agent builders"
```

### Task 8: Remove the builders + providers + grounded twins (in dependency order)

**Files:**
- Delete/trim: `apps/backend/app/agents/cockpit.py`, `apps/backend/app/agents/selfwiki.py`, `apps/backend/app/agents/grounded_search.py`; trim `apps/backend/app/agents/secure_search.py` (KEEP `trim_agentic_content`/`authorized_components`/`_chunk_component` — imported by `access_control_test.py`, `red_team_test.py`, `test_attribution.py`; remove only `SecureAzureAISearchProvider`).
- Modify: `apps/backend/app/api/chat.py` (remove `/cockpit-hosted` 87-97, `/selfwiki-hosted` 100-108).

- [ ] **Step 1: Confirm nothing else imports the symbols being removed**

Run: `cd apps/backend && grep -rn "build_cockpit_agent\|build_selfwiki_agent\|SecureAzureAISearchProvider\|GroundedAzureAISearchProvider" --include='*.py' app eval`
Expected AFTER Task 7: matches only in the files being deleted (no live consumers). If `run_eval` still shows → Task 7 incomplete, STOP.

- [ ] **Step 2: Confirm the trim primitives are STILL imported (must NOT delete)**

Run: `cd apps/backend && grep -rn "trim_agentic_content\|authorized_components\|_chunk_component" --include='*.py' eval`
Expected: the 3 ACL/red-team/attribution tests. These stay.

- [ ] **Step 3: Remove in order** — `build_*_agent` (cockpit.py/selfwiki.py) → then `SecureAzureAISearchProvider` (from secure_search.py) + `GroundedAzureAISearchProvider` (grounded_search.py). Then delete `/cockpit-hosted` + `/selfwiki-hosted` from `chat.py`. **Also retire `eval/grounded_acl_roundtrip_test.py`** (it imports the now-removed `GroundedDomain`; its A-vs-B coverage is superseded by `retrieval_acl_parity_test` + `grounded_archetype_roundtrip_test`). `git rm` it.

- [ ] **Step 4: Verify the three trim tests + boot still green**

Run: `cd apps/backend && uv run python -c "import app.main" && uv run python -m eval.access_control_test && uv run python -m eval.test_attribution`
Expected: import clean; the trim tests unaffected (SKIP cleanly if infra-gated, but must not ImportError).

- [ ] **Step 5: Commit**

```bash
git add -A apps/backend/app/agents apps/backend/app/api/chat.py apps/backend/eval/grounded_acl_roundtrip_test.py
git commit -m "chore: retire grounded agent builders + providers + redundant grounded hosted twins"
```

### Task 9: Frontend — drop grounded `hostedAgentId` + fix stale comments

**Files:**
- Modify: `apps/frontend/lib/domains.ts:60-62,77-78`

- [ ] **Step 1: Edit the two grounded entries**

Remove `hostedAgentId` from `cockpit` (line 62) and `selfwiki` (line 78). Replace the adjacent comment blocks (60-61, 77) — which justify the twins as "MI can invoke, live 403s" — with a one-line note that grounded now runs live-OBO (no twin). Leave `helpdesk` (45) and `platform` (93) `hostedAgentId` intact.

- [ ] **Step 2: Verify the frontend builds / typechecks**

Run: `cd apps/frontend && npm run build` (or `npx tsc --noEmit`).
Expected: no type error; the Live/Hosted toggle simply has no hosted target for grounded (confirm the toggle handles absent `hostedAgentId` — it already does for a domain without one; verify in the runtime route).

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/lib/domains.ts
git commit -m "chore(frontend): drop grounded hosted twins; grounded runs live-OBO"
```

---

## Chunk 6: end-to-end proof

### Task 10: A-vs-B round-trip over the unified archetype

**Files:**
- Create: `apps/backend/eval/grounded_archetype_roundtrip_test.py`
- Modify: `e2e/cockpit-acl.spec.ts`
- Reference: `apps/backend/eval/grounded_acl_roundtrip_test.py`, `apps/backend/eval/grounded_deployed_roundtrip_test.py`.

- [ ] **Step 1: Backend round-trip over the live unified `/cockpit`**

Adapt `grounded_deployed_roundtrip_test.py` to POST to the unified `/cockpit` endpoint as user A and user B and assert on the **cited source filenames** in the `sources` event (NOT the answer prose — B's prose can mention the topic without citing the confidential doc; lesson from the shipped slice). A cites `COCKPIT_CONFIDENTIAL_SOURCE`; B does not. Skip cleanly without infra.

- [ ] **Step 2: Run it**

Run: `cd apps/backend && uv run python -m eval.grounded_archetype_roundtrip_test`
Expected (infra): `✅` A cites confidential, B does not. (Absent: SKIP.)

- [ ] **Step 3: Adapt the browser E2E**

Point `e2e/cockpit-acl.spec.ts` at the unified endpoint (route unchanged: `/d/cockpit` → `/cockpit`). Keep the winning assertion: check the cited source filenames (`.citation-src`), not the answer text. Confirm content-on-click now also works for selfwiki (optional smoke: `/d/selfwiki` shows a snippet on click).

- [ ] **Step 4: Run the E2E**

Run: `cd e2e && npx playwright test cockpit-acl.spec.ts`
Expected: `1 passed`.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/eval/grounded_archetype_roundtrip_test.py e2e/cockpit-acl.spec.ts
git commit -m "test(e2e): A-vs-B ACL round-trip over the unified grounded archetype"
```

---

## Done criteria

- STEP 0 verdict recorded ✅; `retrieve()` body = native agentic retrieve + ACL header over a searchIndex KB (direct-search fallback behind the seam).
- `cockpit-kb` migrated to a `searchIndex` knowledge source; A-vs-B probe green on the production KB before cutover.
- One grounded archetype; `grounded.py` has no `acl`/MCP fork.
- Backend `DomainSpec` registry + `mount_domains` dispatch by kind; `main.py`/`chat.py` no longer hand-wire grounded; the 2-file serving split is gone.
- content-on-click works for **both** grounded domains (800-char cap + URL dedupe preserved).
- `run_eval` scores `retrieve()`; builders + providers + grounded twins removed; trim primitives + their 3 tests intact.
- A-vs-B green: backend round-trip + browser E2E (assert on cited filenames).
- `self_hosted` byte-identical (no behavior change outside the `deployment_mode` gate); keyless throughout.

## Post-plan: selfwiki rollout note

selfwiki has NO per-user ACL, so the native retrieve returns its docs **without** a header (no `permissionFilterOption` on its index). Under the unified archetype it uses the same native-retrieve path over `selfwiki-kb`. Two things to confirm at the selfwiki step (cockpit lands + proves everything first): (1) `selfwiki-kb`'s knowledge source is `searchIndex` (or migrate it, mirroring Task 2b) so the citation-parsing (`docKey` decode) is uniform with cockpit; (2) `selfwiki_search_index` (`tenant.py:51,117`, defaults `selfwiki-docbundles-ks-index`) is populated for the direct-search fallback. selfwiki keeps `acl_group_map=None` → no header attached.
