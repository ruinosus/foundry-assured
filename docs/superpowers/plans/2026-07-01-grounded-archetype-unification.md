# Grounded Archetype Unification — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Collapse the two forked grounded paths (cockpit direct-search+ACL vs selfwiki inline-MCP) into ONE rich grounded archetype fronted by a single `retrieve()` seam, driven by a backend `DomainSpec` registry with dispatch-by-`kind`, keeping the native Microsoft retriever + single head + per-user ACL together.

**Architecture:** A single `retrieve(query, user, domain) -> [{index,source,url,snippet}]` seam owns both retrieval identities (app-MI primary + per-user trim) and hides whether it uses the native retriever+filter (target) or the direct-search Plan B. One archetype (`stream_grounded`) runs the 4 stations (OBO → retrieve → synthesize → emit) for every grounded domain. A backend `DomainSpec` registry mirrors `apps/frontend/lib/domains.ts`; one mount loop dispatches by `kind` (grounded → archetype, workflow → helpdesk, tool → platform). A hard STEP-0 gate proves the native filter before anything is built on it.

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
| `apps/backend/app/services/retrieval.py` | The `retrieve()` seam. Owns both identities. Native-filter path (from STEP 0) OR Plan B (`_direct_search_authorized`). Returns `[{index,source,url,snippet}]`. | Create |
| `apps/backend/app/services/grounded.py` | Collapses to the single archetype `stream_grounded(body, domain, user)` (4 stations) using `retrieve()`. Drop the `acl` fork + `build_responses_kwargs`. Keep `_async_credential`, `build_synthesis_kwargs`, emit invariants. | Modify |
| `apps/backend/app/domains.py` | Backend `DomainSpec` registry (mirrors `domains.ts`) + `mount_domains(app)` loop dispatching by `kind`. | Create |
| `apps/backend/app/api/chat.py` | Remove the grounded `/cockpit` + `/selfwiki` router endpoints (moved into the mount loop) and the two redundant grounded hosted twins. | Modify |
| `apps/backend/app/main.py` | Replace the hand-wired helpdesk/platform mounts + the grounded comment block with `mount_domains(app)`. | Modify |
| `apps/backend/eval/run_eval.py` | Rewire `agent_factory` off `build_*_agent` onto `retrieve()`. | Modify |
| `apps/backend/app/agents/{cockpit,selfwiki,secure_search,grounded_search}.py` | Remove the builders + provider classes AFTER run_eval is rewired. Keep the trim primitives in `secure_search.py` (tests import them). | Modify/Delete |
| `apps/frontend/lib/domains.ts` | Drop `hostedAgentId` from cockpit+selfwiki and update the now-stale twin-justification comments. | Modify |
| `apps/backend/eval/grounded_archetype_roundtrip_test.py` | A-vs-B ACL round-trip over the unified archetype's `retrieve()`. | Create |
| `e2e/cockpit-acl.spec.ts` | Adapt the browser A-vs-B assertion to the unified endpoint. | Modify |

**Rollout order:** cockpit first (has ACL — the hard case), then selfwiki. helpdesk/platform enter the registry without touching internals.

---

## Chunk 1: STEP 0 — the native-filter gate

**This gate precedes everything. Do not start Chunk 2 until this task reports ✅ or ❌ with the captured shape.** The result decides whether `retrieve()`'s body is the native filter or Plan B — either way it lands in the same interface, so Chunks 3–6 are unaffected.

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

Create `docs/superpowers/plans/2026-07-01-grounded-archetype-unification-STEP0-findings.md` capturing: verdict, the exact filter field name + syntax (if ✅), the api-version, and the annotation→`{source,url,snippet}` mapping for the native path. This file is the input to Task 2.

- [ ] **Step 4: Commit**

```bash
git add apps/backend/eval/step0_native_filter_probe.py docs/superpowers/plans/2026-07-01-grounded-archetype-unification-STEP0-findings.md
git commit -m "test(step0): probe native-retriever group-filter trim + api-version (unification gate)"
```

**Gate decision:** ✅ → Task 2 implements the native-filter body. ❌ → Task 2 implements Plan B (`_direct_search_authorized`) as the body and the native path is deferred behind the same interface. Everything downstream is identical.

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

- [ ] **Step 3: Implement `retrieve()`**

Author the body per the STEP-0 gate decision. The signature and identity-ownership are fixed regardless:

```python
# app/services/retrieval.py
"""The single grounded retrieval seam. Owns BOTH retrieval identities so the archetype
(stations 1/3/4) never touches search credentials:
  - primary search auth = the APP managed identity (Search Index Data Reader). End users have no
    search RBAC, so the user token can NEVER be the primary.
  - per-user trim      = the signed-in user (the native filter's group values [STEP 0] OR the
    x-ms-query-source-authorization header in Plan B — grounded._direct_search_authorized).
Returns authorized docs as [{index, source, url, snippet}] — deduped by URL, 1-based index.
Fail-closed: a source with no declared access never enters the result (rule #6)."""
from __future__ import annotations

_SEARCH_SCOPE = "https://search.azure.com/.default"

async def retrieve(query: str, user, domain, *, top: int = 8) -> list[dict]:
    from azure.identity.aio import DefaultAzureCredential as _AppCredential
    app_cred = _AppCredential()
    try:
        primary = (await app_cred.get_token(_SEARCH_SCOPE)).token   # app MI
        user_token = await _user_search_token(user)                 # OBO, or None (dev/no-auth)
        # --- body per STEP 0 ---
        # ✅ native filter:   rows = await _native_retrieve(domain, query, primary, _groups(user), top)
        # ❌ plan B:          rows = await _direct_search_authorized(domain, query, primary, user_token, top=top)
        return _project(rows)   # -> [{index,source,url,snippet}], deduped by URL, 1-based
    finally:
        import contextlib
        with contextlib.suppress(Exception):
            await app_cred.close()
```

`_project()` centralizes the dedup+index invariant (moved out of `stream_grounded_agui`). For Plan B, `_direct_search_authorized` already returns the right shape — `_project` is a passthrough/dedupe. `_user_search_token(user)` mirrors the OBO logic in `grounded._async_credential` (returns `None` when `not settings.auth_enabled or user is None`).

If STEP 0 was ❌, `_native_retrieve` is NOT written (YAGNI) — only Plan B. If ✅, `_native_retrieve` is authored from the STEP-0 findings shape (api-version + filter field verbatim). Leave `# TODO: verify signature` on any field STEP 0 didn't nail.

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.retrieval_shape_test`
Expected: PASS (`✅ retrieve() contract holds`).

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/services/retrieval.py apps/backend/eval/retrieval_shape_test.py
git commit -m "feat(retrieval): single retrieve() seam owning both identities (native-filter|planB per STEP0)"
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
- Test: `apps/backend/eval/grounded_payload_test.py` (existing — keep green), `apps/backend/eval/archetype_emit_test.py` (create)

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
- Keep `_async_credential(user)` (OBO for the *inference* call — station 1). Remove `_source_from_annotation` and `CITATION_DIRECTIVE` (MCP-only, now dead). Remove the `acl`/`search` no-longer-needed fields from the old `GroundedDomain` (superseded by `DomainSpec`, Task 5) — or keep `GroundedDomain` as a thin alias if other eval modules import it; check `grep -rn GroundedDomain eval app`.

- [ ] **Step 4: Run both tests**

Run: `cd apps/backend && uv run python -m eval.archetype_emit_test && uv run python -m eval.grounded_payload_test`
Expected: both PASS. Also `uv run python -c "import app.main"` still imports.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/services/grounded.py apps/backend/eval/archetype_emit_test.py
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
    acl_group_map: dict | None = None   # ACL is DATA (rule #6); None/empty → no-op filter
    hosted_agent_name: str | None = None

def _domains() -> list[DomainSpec]:
    from app.agents.prompts import COCKPIT_INSTRUCTIONS, SELFWIKI_INSTRUCTIONS
    from app.core.tenant import tenant_config
    cfg = tenant_config()
    return [
        DomainSpec("helpdesk", "workflow", hosted_agent_name=cfg.hosted_agent_name),
        DomainSpec("cockpit", "grounded", COCKPIT_INSTRUCTIONS,
                   kb_name=cfg.cockpit_search_knowledge_base, search_index=cfg.cockpit_search_index,
                   acl_group_map=cfg.cockpit_acl_group_map),   # DATA, from config
        DomainSpec("selfwiki", "grounded", SELFWIKI_INSTRUCTIONS,
                   kb_name=cfg.selfwiki_search_knowledge_base, search_index=cfg.selfwiki_search_index),
        DomainSpec("platform", "tool"),
    ]

def mount_domains(app) -> None:
    """One loop, dispatch by kind. self_hosted byte-identical: the gate is _domain_deps (shared-mode
    only adds the entitlement dep)."""
    from app.main import _domain_deps   # or move _domain_deps here and import into main
    for d in _domains():
        if d.kind == "grounded":
            _mount_grounded(app, d)
        elif d.kind == "workflow":
            _mount_helpdesk(app, d)      # existing add_agent_framework_fastapi_endpoint logic
        elif d.kind == "tool":
            _mount_platform(app, d)      # existing platform_agent_proxy logic
```

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

Add the missing config fields (`cockpit_acl_group_map`, `selfwiki_search_index`) to `app/core/tenant.py` with safe defaults (empty → no-op / fail-closed). `selfwiki_search_index` is needed for Plan B direct-search over selfwiki; default empty until selfwiki rollout.

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

- [ ] **Step 1: Inspect how `agent_factory` is consumed**

Read `run_eval.py` around 230-260 to see what the golden harness calls on `agent_factory` (build → run → collect answer+citations). The replacement must expose the SAME observable output (answer text + cited sources) sourced from `retrieve()` + one synthesis call.

- [ ] **Step 2: Replace the factory**

Swap `agent_factory = build_cockpit_agent` / `build_selfwiki_agent` for a small local helper that, per golden row, builds the `DomainSpec` for the domain, calls `retrieve()`, synthesizes (reuse `build_synthesis_kwargs`), and returns answer+sources in the shape the harness scores. Remove the `from app.agents.cockpit/selfwiki import build_*_agent` imports.

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

- [ ] **Step 3: Remove in order** — `build_*_agent` (cockpit.py/selfwiki.py) → then `SecureAzureAISearchProvider` (from secure_search.py) + `GroundedAzureAISearchProvider` (grounded_search.py). Then delete `/cockpit-hosted` + `/selfwiki-hosted` from `chat.py`.

- [ ] **Step 4: Verify the three trim tests + boot still green**

Run: `cd apps/backend && uv run python -c "import app.main" && uv run python -m eval.access_control_test && uv run python -m eval.test_attribution`
Expected: import clean; the trim tests unaffected (SKIP cleanly if infra-gated, but must not ImportError).

- [ ] **Step 5: Commit**

```bash
git add -A apps/backend/app/agents apps/backend/app/api/chat.py
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

- STEP 0 verdict recorded; `retrieve()` body matches it.
- One grounded archetype; `grounded.py` has no `acl`/MCP fork.
- Backend `DomainSpec` registry + `mount_domains` dispatch by kind; `main.py`/`chat.py` no longer hand-wire grounded; the 2-file serving split is gone.
- content-on-click works for **both** grounded domains (800-char cap + URL dedupe preserved).
- `run_eval` scores `retrieve()`; builders + providers + grounded twins removed; trim primitives + their 3 tests intact.
- A-vs-B green: backend round-trip + browser E2E (assert on cited filenames).
- `self_hosted` byte-identical (no behavior change outside the `deployment_mode` gate); keyless throughout.

## Post-plan: selfwiki rollout note

selfwiki has no `search_index` today (it used the MCP tool). For the unified archetype it needs one for Plan B (or the native-filter path with an empty group map). Set `selfwiki_search_index` + re-ingest if needed as the selfwiki step of rollout — cockpit lands first and proves the path.
