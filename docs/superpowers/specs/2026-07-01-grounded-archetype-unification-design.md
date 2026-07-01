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

The only conflict is **(1)↔(3)**: the native agentic `knowledge_base_retrieve` path does **not** honor the automatic per-user `x-ms-query-source-authorization` header (verified; azure-sdk-for-python#44454). This design reconciles them with a **pre-retrieval security filter** (§4), gated by a **STEP 0** that must prove the native retriever accepts it — with a mapped **Plan B** if it doesn't.

Non-goals: merging knowledge bases (each domain keeps its **own isolated KB**); changing helpdesk's workflow internals or platform's tool internals; changing `self_hosted` behavior (byte-identical where the `deployment_mode` seam applies).

## 3. Architecture

### 3.1 The rich grounded archetype

A single assembly line with a clean contract. It receives `(question, user, domain_spec)` and returns the AG-UI SSE stream. Four stations:

1. **Identity (OBO)** — run as the signed-in user. The user is **captured in the endpoint and passed as an argument** — never read from the `current_user()` contextvar, which is lost inside the `StreamingResponse` async generator (verified; the bug that silently fell back to the app MI and 403'd). Preserved from the shipped design.
2. **Retrieve** — call the **native retriever** with a **security filter** built from the user's group claims (§4). Returns `[{index, source, url, snippet}]`. A domain with no confidential content passes an empty filter (no-op). **Fail-closed:** a source with no declared access does not enter the result.
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

## 4. The retrieval reconciliation (STEP 0 gate)

### 4.1 Native retriever + pre-retrieval security filter (target)

Instead of the automatic per-user header (ignored on the agentic path), compute the user's authorized groups from their token and pass them as an **explicit search filter** to the native retriever, applied **at retrieval time**. Because the filter is applied *during* retrieval, the retriever **never sees nor reasons over** unauthorized documents → fail-closed **and** native.

This is categorically different from the **rejected** "post-filter" approach (retrieve everything with the native retriever, hide disallowed citations afterward): there the model already read and reasoned over confidential content, so the prose can leak it even with the citation hidden. **The distinction is WHEN the filter applies: before/during (safe) vs after (leaks).**

> **Project rule #1 (do not invent SDK signatures).** Whether the native Foundry IQ retriever accepts a caller-supplied group filter is **UNVERIFIED**. The agentic path ignores the *header*; a *filter* is a different mechanism and MAY be honored. This must be confirmed against `learn.microsoft.com/azure/foundry` + `microsoft-foundry/foundry-samples` before any code depends on it. Until confirmed, the retrieval call is STEP-0-provisional.
>
> **`api-version` is itself part of STEP 0.** Today one constant `_KB_API = "2026-05-01-preview"` (`grounded.py:34`) is shared by both the MCP `server_url` and the direct-search `docs/search` URL. The filter surface, **if** it exists, may require a *different* api-version — STEP 0 must probe the version independently, not assume the pinned one.

### 4.2 STEP 0 (hard gate, first thing built)

STEP 0 proves — as a runnable `eval/` module — that the native retriever **trims by a caller-supplied group filter**, using two users (one in the confidential group, one not) against a doc that only the first may read:

- ✅ **Filter honored** → `retrieve()` uses the native retriever + filter. The owner gets all three (native + single head + ACL).
- ❌ **Filter ignored** → `retrieve()`'s body falls back to **Plan B**: our own lightweight query planning over the **direct-search-as-user** path (which already trims per-user via `x-ms-query-source-authorization` — proven in `_direct_search_authorized`). We keep single head + ACL + content, and lose only the *managed* native retriever on grounded (owning retrieval tuning ourselves). Adaptive planning (simple question → one sub-query) bounds the added cost/latency.

**Nothing is built on top until STEP 0 closes.** Either outcome lands in the same `retrieve()` interface, so §3's shape is unchanged regardless.

If Microsoft later honors per-user ACL on the native agentic path, `retrieve()`'s body swaps to it — a welcome change, not a refactor.

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

Rollout order: **cockpit first** (the hard case — it has ACL), then **selfwiki** (same path, empty filter). helpdesk/platform enter the registry without touching their internals.

Constraints held throughout: keyless / `DefaultAzureCredential` + OBO (no API keys); ACL is **data**, not code (rule #6); `self_hosted` byte-identical where the `deployment_mode` seam applies; every grounded answer carries ≥1 citation (rule #4).

## 7. Risks

| Risk | Mitigation |
|------|------------|
| Native retriever rejects the filter | STEP 0 gates it; Plan B (§4.2) mapped and lands in the same interface |
| DIY planning (Plan B) retrieves worse than native | STEP 0 / a small recall check on the corpus before committing; adaptive planning bounds cost |
| Eval refactor changes what's measured | Point eval at `retrieve()` so it measures the production path; keep the golden set unchanged |
| `deployment_mode` regression | Gate any behavior change behind `settings.deployment_mode`; `self_hosted` stays byte-identical |

## 8. Open questions

- Exact native-retriever filter surface + `api-version` (STEP 0 resolves; rule #1).
- Whether `/platform-hosted` remains the only tool twin or also gains a live path later (out of scope here).
