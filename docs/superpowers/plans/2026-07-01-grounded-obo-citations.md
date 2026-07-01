# Grounded Structured Citations (OBO + Responses + Foundry IQ MCP tool) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the grounded agents (Cockpit, then Selfwiki) return structured, clickable citations — the Microsoft-indicated way — while enforcing per-user document-level ACL (Cockpit), by calling the Responses API on-behalf-of the signed-in user with the knowledge base attached as a Foundry IQ `knowledge_base_retrieve` MCP tool, replacing today's regex-from-text `EvidencePanel`.

**Architecture:** `/cockpit` and `/selfwiki` move off the agent-framework AG-UI adapter and become thin FastAPI **router endpoints** (like `/helpdesk-hosted`) that call a new `app/services/grounded.py::stream_grounded_agui`. That bridge runs a **Responses API** call as the signed-in user (OBO for `https://ai.azure.com/.default` → no 403), attaches the KB as an inline **MCP tool** (`knowledge_base_retrieve`), and — for Cockpit only — passes the user's search-scoped OBO token as the `x-ms-query-source-authorization` header (per-user ACL). It re-emits the Responses stream as AG-UI (text deltas + a `sources` channel carrying structured citations). The frontend `EvidencePanel` renders those citations as clickable footnotes (click → the retrieved content).

**Tech Stack:** Python 3.12 + `uv`, `azure-ai-projects>=2.2.0` (Responses API, `2026-05-01-preview`), `ag_ui` (AG-UI events), FastAPI; Next.js 15 + CopilotKit v2 (`useAgent`); Playwright E2E. Auth: `OnBehalfOfCredential` (rule #2, keyless). Tests: runnable `def main()` modules in `apps/backend/eval/`, run with `uv run python -m eval.<name>` (NO pytest).

**Spec:** [`docs/superpowers/specs/2026-07-01-grounded-obo-citations-design.md`](../specs/2026-07-01-grounded-obo-citations-design.md). Read §2, §3, §5, §8 before starting. Microsoft-pattern proof is in §8.

**Non-negotiables (from CLAUDE.md + spec):**
- **Rule #1** — no invented SDK signatures. The inline Responses+MCP-tool shape is **STEP-0-provisional**; Chunk 0 is a hard gate. Where a shape is not yet verified, the step says so and points at the STEP 0 finding — never guess.
- **Rule #2** — keyless / OBO; no API keys.
- **self_hosted byte-identical** where applicable; shared-mode paths stay mode-gated behind `settings.deployment_mode == "shared"`.
- **Scope:** PoC = Cockpit; rollout = Selfwiki. Helpdesk workflow and the hosted twins stay as-is this slice (the Live/Hosted toggle remains; the hosted twins are the preview fallback).
- **Test convention:** mirror `apps/backend/eval/access_control_test.py` — a runnable `def main()` that prints `PASS`/`FAIL` and `sys.exit(0|1)`; infra-free tests must not touch Azure; infra-gated tests skip cleanly (print SKIP + `sys.exit(0)`) when their env vars are absent, NEVER fabricate a pass.

---

## Chunk 0: STEP 0 — verification spike (HARD GATE — blocks Chunks 1–4)

**Purpose.** Turn every `⟨S0⟩` provisional shape in the spec into a verified fact BEFORE any product code. This chunk ships **no product code** — only throwaway spike modules under `eval/` and a **findings note** appended to the plan. If any of (a)/(b)/(c)/(frontend) is red, STOP and surface to the human; the approach may change.

**Files:**
- Create (throwaway spike): `apps/backend/eval/step0_grounded_citations_spike.py`
- Create (findings): `docs/superpowers/plans/2026-07-01-grounded-obo-citations-STEP0-findings.md`
- Reference: `apps/backend/app/services/hosted.py` (Responses client construction pattern), `apps/backend/app/core/auth.py` (`credential_for_request`), `apps/backend/app/agents/secure_search.py` (existing `x_ms_query_source_authorization` usage), spec §2/§5/§8.

- [ ] **Step 1: Write the spike scaffold (infra-gated, prints SKIP without creds)**

Create `eval/step0_grounded_citations_spike.py` with a `def main()` that reads env (`AZURE_SEARCH_ENDPOINT`, `FOUNDRY_PROJECT_ENDPOINT`, `COCKPIT_SEARCH_KNOWLEDGE_BASE`, and the two test users used by `access_control_test.py`). If the infra env is missing, print `SKIP: STEP 0 needs live Foundry+Search` and `sys.exit(0)`. This is a spike: it is allowed to print raw SDK objects; it is NOT shipped as a product test.

- [ ] **Step 2: (shape + b) Prove the inline Responses + MCP-tool call runs as the user with no 403**

In the spike, build a Responses client **as the signed-in user** (reuse the `hosted.py` pattern: `AIProjectClient(endpoint, credential=<OBO>, allow_preview=True).get_openai_client()`, where `<OBO>` is `credential_for_request()` after setting `_current_user`; for the spike you may mint the OBO from a test-user ROPC token as `access_control_test.py` does). Call `responses.create(input=<probe>, instructions=<cite directive>, tools=[{type:"mcp", server_label:"knowledge-base", server_url:f"{search}/knowledgebases/{kb}/mcp?api-version=2026-05-01-preview", allowed_tools:["knowledge_base_retrieve"], require_approval:"never"}], stream=False)`.
- **Resolve the A1-vs-A2 question:** first try WITHOUT `project_connection_id` (A1). If it fails auth to reach the MCP endpoint, create a `RemoteTool` project connection per spec §8 (`authType=ProjectManagedIdentity`, `audience=https://search.azure.com/`, target = the mcp endpoint) and retry WITH `project_connection_id` (A2). Record which worked.
- **Assert:** HTTP 200 (no 403 on raw inference under the user token) → confirms spec §5(b).

- [ ] **Step 3: (a) Capture the citation/annotation structure and PRODUCE THE MAPPING**

Print the full `response` object shape: `output_text`, any `annotations`, the `References:` block, and every streamed event `type` when `stream=True` (e.g. `response.output_text.delta`, any `…annotation.added`). **Deliverable:** in the findings note, write the concrete mapping `annotation → {index, source, url, content}` (spec §3), including where the source name and the retrieved text live, and the exact inline marker string emitted (expected `【message_idx:search_idx†source_name】`). Note the citation-URL caveat (search-index KB URL falls back to the MCP endpoint — spec §8): confirm whether any usable `url` is present or if `content` is the only click target.

- [ ] **Step 4: (c) Prove the `x-ms-query-source-authorization` header trims by document — on OUR service version**

Requires the ACL prerequisite to exist for at least one probe doc. **`access_control_test.py` does NOT stamp — it assumes an already-stamped `cockpit-kb`** (it only runs the agentic retrieve as two ROPC users), so it is not a shortcut here. **You MUST run the Chunk 2 stamp first:** pull **Chunk 2 Steps 1 + 4 forward into this gate** (author the minimal classification, then run `ingest_cockpit` with `COCKPIT_ACL_CLASSIFICATION` set so `setup_acl` stamps the `groups` field + enables `permissionFilterOption`). Then run the Step-2 call twice: once with the header = user A's search-OBO token, once with user B's (public-only). **Assert:** A's retrieved sources include the confidential doc and B's do not (spec §5 test). Record whether the header trims (Nov-2025 behavior) or is still "inert" on our service version.
- **Contingency (spec §5 issue #5):** if it does NOT trim, record it — Chunk 1 must then KEEP the app-side trim (`secure_search.py` layer B) instead of deleting it, and Chunk 2/4's ACL claim shifts to the app-side path.

- [ ] **Step 5: (frontend) Prove the `sources` channel reaches `useAgent`**

Stand up a throwaway backend route that emits one AG-UI `CUSTOM` event `{name:"sources", value:[{index:1, source:"probe", content:"hello"}]}` after a short text message, register it as a temporary HttpAgent, and in the browser log whether CopilotKit v2 `useAgent`'s `agent` object surfaces it (subscribe to everything available; inspect `agent.messages` and any event/state callbacks). **Assert:** the `sources` payload is observably reachable. If NOT reachable, record the fallback decision: carry citations as a **structured trailer in the assistant message** (a machine-readable block the panel parses from `agent.messages`, which it already reads). This decision drives Chunk 1 Step (emit) and Chunk 3.

- [ ] **Step 6: Write the findings note + GO/NO-GO**

Fill `…-STEP0-findings.md` with: the working call shape (A1 or A2 + whether a project connection is needed), the annotation→sources mapping, the no-403 result, the ACL-trim result (+ contingency if red), and the frontend-channel decision (CUSTOM vs message-trailer). End with **GO** (all green) or **NO-GO** (which item is red + recommended approach change). Commit.

```bash
git add apps/backend/eval/step0_grounded_citations_spike.py docs/superpowers/plans/2026-07-01-grounded-obo-citations-STEP0-findings.md
git commit -m "step0: verify grounded citations shape/no-403/ACL-trim/frontend-channel (gate)"
```

- [ ] **Step 7: GATE — do not proceed unless the findings note says GO.** If NO-GO, stop and surface to the human.

---

## Chunk 1: Backend — `stream_grounded_agui` + router endpoints

**Depends on:** Chunk 0 GO (uses the confirmed call shape + frontend-channel decision + ACL-trim result).

**Files:**
- Create: `apps/backend/app/services/grounded.py`
- Modify: `apps/backend/app/api/chat.py` (add `/cockpit`, `/selfwiki` router endpoints)
- Modify: `apps/backend/app/main.py:97-115` (remove the agent-framework adapter mounting of `/cockpit` + `/selfwiki`)
- Modify (fate per spec §3 issue #6): `apps/backend/app/agents/cockpit.py`, `apps/backend/app/agents/selfwiki.py` — see Step 7
- Create (test): `apps/backend/eval/grounded_payload_test.py`

### Design of `grounded.py` (interfaces)

```python
from dataclasses import dataclass

@dataclass(frozen=True)
class GroundedDomain:
    """Per-domain config for the grounded citations bridge (spec §3 domain_cfg)."""
    kb_name: str          # tenant_config().cockpit_search_knowledge_base / selfwiki_search_knowledge_base
    instructions: str     # COCKPIT_INSTRUCTIONS / SELFWIKI_INSTRUCTIONS + the cite directive
    acl: bool             # True = attach x-ms-query-source-authorization (Cockpit); False = omit (Selfwiki)

async def stream_grounded_agui(body: dict, domain: GroundedDomain) -> AsyncGenerator[str]:
    ...
```

- [ ] **Step 1: Write the failing infra-free payload test**

Create `eval/grounded_payload_test.py` (mirror the runnable-`main()` convention). It imports a pure helper `build_responses_kwargs(user_text, domain, model_token, search_token)` from `grounded.py` and asserts, WITHOUT touching Azure:
- the MCP tool dict has `type=="mcp"`, `allowed_tools==["knowledge_base_retrieve"]`, `require_approval=="never"`, and `server_url` ends with `/knowledgebases/{domain.kb_name}/mcp?api-version=2026-05-01-preview`;
- when `domain.acl is True` the tool `headers` contains `x-ms-query-source-authorization` == the search token; when `domain.acl is False` there is NO such header;
- `instructions` includes the `【message_idx:search_idx†source_name】` directive.

```python
def main() -> None:
    from app.services.grounded import GroundedDomain, build_responses_kwargs
    ck = GroundedDomain(kb_name="cockpit-kb", instructions="X", acl=True)
    kw = build_responses_kwargs("q", ck, model_token="M", search_token="S")
    tool = kw["tools"][0]
    assert tool["type"] == "mcp" and tool["allowed_tools"] == ["knowledge_base_retrieve"]
    assert tool["server_url"].endswith("/knowledgebases/cockpit-kb/mcp?api-version=2026-05-01-preview")
    assert tool["headers"]["x-ms-query-source-authorization"] == "S"
    sw = GroundedDomain(kb_name="selfwiki-kb", instructions="Y", acl=False)
    assert "headers" not in build_responses_kwargs("q", sw, "M", "S")["tools"][0]
    print("PASS"); sys.exit(0)
```

- [ ] **Step 2: Run it to verify it fails**

Run: `cd apps/backend && uv run python -m eval.grounded_payload_test`
Expected: FAIL — `ModuleNotFoundError` / `ImportError: build_responses_kwargs`.

- [ ] **Step 3: Implement `build_responses_kwargs` + `GroundedDomain` (pure, infra-free)**

In `grounded.py`, implement `GroundedDomain` and `build_responses_kwargs(user_text, domain, model_token, search_token)` returning the exact kwargs dict from the **Chunk 0 findings** (A1 inline, or add `project_connection_id` if the findings said A2). Build the MCP tool dict; add the ACL header only when `domain.acl`. Keep it a pure function (no I/O) so the test stays infra-free.

- [ ] **Step 4: Run the test to verify it passes**

Run: `cd apps/backend && uv run python -m eval.grounded_payload_test`
Expected: `PASS`.

- [ ] **Step 5: Implement `stream_grounded_agui` (the AG-UI bridge)**

Mirror `hosted.py::stream_agui` (reuse `_last_user_text`, the `RunStarted/TextMessageStart/Content/End/RunFinished/RunError` framing, `EventEncoder`). Differences:
- Build the Responses client **as the user**: obtain the model-scope OBO token via `credential_for_request().get_token("https://ai.azure.com/.default")` and construct the client the way Chunk 0 confirmed; obtain the search-scope token via `credential_for_request().get_token("https://search.azure.com/.default")` **only when `domain.acl`**.
- Call `responses.create(**build_responses_kwargs(...), stream=True)`.
- Stream handling per Chunk 0 findings: forward text deltas as `TextMessageContentEvent`; collect annotations into a `sources` list using the findings' mapping.
- On completion, emit the citations on the **channel Chunk 0 chose**: either an AG-UI `CUSTOM` event `{name:"sources", value:[...]}` (if reachable) OR the structured message-trailer (append a machine-readable block to the assistant text before `TextMessageEndEvent`). Then `RunFinishedEvent`.
- Keep the `except Exception` → `RunErrorEvent` path (surface 403/500 cleanly), exactly like `stream_agui`.

- [ ] **Step 6: Add the router endpoints in `chat.py`**

Add `/cockpit` and `/selfwiki` POST endpoints next to the `*-hosted` ones. Use `_hosted_deps("cockpit")` / `_hosted_deps("selfwiki")` (same shared-mode domain gate as the adapter used). Each builds its `GroundedDomain` from `tenant_config()` (+ the domain instructions from `app.agents.prompts`) and returns `StreamingResponse(stream_grounded_agui(body, domain), media_type="text/event-stream")`. Cockpit → `acl=True`; Selfwiki → `acl=False`.

```python
@router.post("/cockpit", dependencies=_hosted_deps("cockpit"))
async def cockpit(request: Request) -> StreamingResponse:
    from app.agents.prompts import COCKPIT_INSTRUCTIONS
    from app.services.grounded import GroundedDomain, stream_grounded_agui
    cfg = tenant_config()
    domain = GroundedDomain(kb_name=cfg.cockpit_search_knowledge_base,
                            instructions=COCKPIT_INSTRUCTIONS, acl=True)
    return StreamingResponse(stream_grounded_agui(await request.json(), domain),
                             media_type="text/event-stream")
```

- [ ] **Step 7: Remove the adapter mounting in `main.py` + resolve the builders' fate**

In `main.py`, delete the `if cockpit_configured(): add_agent_framework_fastapi_endpoint(... path="/cockpit" ...)` block and the equivalent `/selfwiki` block (lines ~97–115) — the router now owns those paths. Remove the now-unused imports (`build_cockpit_agent`, `cockpit_configured`, `build_selfwiki_agent`, `selfwiki_configured`, and `_grounded_agent` if nothing else uses it — check `platform` first).
- **Builders' fate (spec §3 issue #6):** the in-repo `build_cockpit_agent` / `build_selfwiki_agent` are the LIVE-path builders (the hosted twins have their own build under `apps/hosted-*`). Per the Chunk 0 ACL-trim result:
  - **If the header trims (GO):** the live path no longer needs `SecureAzureAISearchProvider`; **delete** `build_cockpit_agent`/`build_selfwiki_agent` + `cockpit.py`/`selfwiki.py` if nothing else imports them (grep first: `rg build_cockpit_agent apps/backend`). Keep `secure_search.py` only if `access_control_test.py`/Chunk 4 still exercise the app-side trim as a regression.
  - **If the header does NOT trim (contingency):** KEEP the app-side trim path; `stream_grounded_agui` must additionally apply `secure_search.trim_agentic_content` to the retrieved chunks before the model — do NOT delete `secure_search.py`.

- [ ] **Step 8: Boot check + commit**

Run: `cd apps/backend && uv run python -c "import app.main"` (import-time wiring is valid). Then `uv run python -m eval.grounded_payload_test` → `PASS`.

```bash
git add apps/backend/app/services/grounded.py apps/backend/app/api/chat.py apps/backend/app/main.py apps/backend/eval/grounded_payload_test.py
git commit -m "feat(grounded): live citations via Responses+MCP OBO bridge; /cockpit /selfwiki become router endpoints"
```

---

## Chunk 2: ACL prerequisite — re-ingest cockpit-kb with permission metadata (Cockpit only)

**Depends on:** Chunk 0 GO. Only needed if the header trims (else the app-side trim in Chunk 1 Step 7 covers ACL and this chunk provides the group stamping for that path instead). **Infra-gated** — this touches the live cockpit-kb index; the plan documents it as a runbook + a verification test, and skips cleanly without creds.

**Files:**
- Create (minimal classification, gitignored): `apps/backend/.cockpit-acl-poc.json`
- Modify: repo-root `.gitignore` (add the classification file — there is no `apps/backend/.gitignore` today)
- Reference: `apps/backend/app/knowledge/ingest_cockpit.py`, `apps/backend/app/knowledge/acl_setup.py`, `apps/backend/eval/access_control_test.py`
- Create (test): `apps/backend/eval/cockpit_acl_stamp_test.py`

> The ingest already owns ACL (`ingest_cockpit.main` → `setup_acl(component_groups or None)` when `tenant_config().acl_group_map` is set; `setup_acl` adds the `groups` permission field + `permissionFilterOption=enabled`). Because the aap-kb manifests have `groups: None`, `component_groups` collapses to `{}` → `None`, so `setup_acl` uses the **external `COCKPIT_ACL_CLASSIFICATION` map** — which is exactly the PoC classification below. So the "re-ingest with permission metadata" is mostly **configuration + a minimal classification**, not new pipeline code.

- [ ] **Step 1: Author the minimal PoC classification (makes the A-vs-B test meaningful — spec §5 issue #4)**

Create `.cockpit-acl-poc.json` = `{ "<canonical-component-key>": ["confidential"] }` mapping ONE specific component (whose content answers a chosen probe query) to a group only test-user **A** is in.
- **Group names MUST resolve** via `tenant_config().acl_group_map` — the only resolvable names are the demo trio **`public` / `internal` / `confidential`** (from `cockpit_acl_public_group` / `_internal_group` / `_confidential_group`) plus any custom entries in `cockpit_acl_group_map`. `acl_setup._resolve()` **drops** any unknown non-GUID name → `groups: []` → fail-closed to *nobody* (which would make A *also* lose the doc — a false negative). So use **`confidential`** (test-user A in that group), NOT an invented label like `cockpit-confidential`. Set `cockpit_acl_default_groups="public"` so every other doc → `public` (both A and B see it).
- **The classification KEY is the canonical component key** produced by `acl_setup._component(blob_url)` → `_canonical()`: `<component>` lowercased, spaces→hyphens, trailing version stripped (e.g. `cockpit-portal-api`); source pages are `source__<NAME>`. Look at a stamped blob name / the `access_control_test.py` `_chunk_component` logic to pick a real key. A wrong key silently stamps nothing.
- Pick the probe query so its top answer lives in that confidential component.
- Add `apps/backend/.cockpit-acl-poc.json` to the **repo-root `.gitignore`** (create `apps/backend/.gitignore` with the entry if you prefer per-dir) — the corpus + access map are never committed (see `acl_setup.py` docstring).

- [ ] **Step 2: Write the failing verification test (infra-gated)**

Create `eval/cockpit_acl_stamp_test.py`: after stamping, GET the index and assert (a) a `groups` field exists with `permissionFilter=="groupIds"`, (b) `permissionFilterOption=="enabled"`, (c) the confidential doc's `groups` contains the resolved object-id of the `confidential` group (`tenant_config().acl_group_map["confidential"]`), (d) at least one public doc has the `public` group. Without `AZURE_SEARCH_ENDPOINT` + creds → print `SKIP` + `sys.exit(0)`.

- [ ] **Step 3: Run it to verify it fails (or SKIPs)**

Run: `cd apps/backend && uv run python -m eval.cockpit_acl_stamp_test`
Expected: FAIL (no `groups` field yet) with live creds; SKIP without.

- [ ] **Step 4: Run the re-ingest with ACL enabled (runbook)**

Ensure the demo-trio group object-ids are set so `tenant_config().acl_group_map` resolves `confidential` (`cockpit_acl_confidential_group`) and `public` (`cockpit_acl_public_group`), then:
```bash
cd apps/backend
COCKPIT_DOCBUNDLES=/path/to/aap-kb/apps/agent/docbundles \
COCKPIT_ACL_CLASSIFICATION=$PWD/.cockpit-acl-poc.json \
  uv run python -m app.knowledge.ingest_cockpit
```
This uploads, (re)builds the KB, runs the indexer to completion, and stamps document-level access (`ingest_cockpit.py:308-314`).

- [ ] **Step 5: Run the verification test to confirm the stamp**

Run: `cd apps/backend && uv run python -m eval.cockpit_acl_stamp_test`
Expected: `PASS` (field present, option enabled, confidential doc stamped).

- [ ] **Step 6: Commit (the test + .gitignore entry; NOT the classification JSON or corpus)**

```bash
git add apps/backend/eval/cockpit_acl_stamp_test.py .gitignore   # root .gitignore now ignores the PoC classification
git commit -m "test(acl): verify cockpit-kb permission-metadata stamping for per-user trimming"
```

---

## Chunk 3: Frontend — structured citations in `EvidencePanel`

**Depends on:** Chunk 0 (which channel) + Chunk 1 (the backend emits it).

**Files:**
- Modify: `apps/frontend/components/console/EvidencePanel.tsx`
- Modify: `apps/frontend/styles/globals.css` (footnote + modal styles)
- Reference: spec §3 (click → content, NOT url, for search-index KBs)

- [ ] **Step 1: Read the citations off the chosen channel**

In `EvidencePanel`, replace the regex `extractSources` for grounded domains with a subscription to the **Chunk-0 channel**: if CUSTOM events are reachable, subscribe to the `sources` event via the API Chunk 0 identified; else parse the structured message-trailer out of the last assistant message (the panel already reads `agent.messages`). Keep the regex path as a graceful fallback when no structured citations are present (so behavior degrades, never throws). Type: `interface Citation { index: number; source: string; url?: string; content?: string }`.

- [ ] **Step 2: Render structured, numbered, clickable footnotes**

Render each citation as a numbered chip/footnote `[n] source`. On click: if `url` is present (blob KBs) open it; else open a modal/expander showing `content` (spec §8: search-index KB URLs fall back to the MCP endpoint, so `content` is the reliable display). Keep the existing "Garantias" section and the empty-state placeholder. Update the title count to the citation count.

- [ ] **Step 3: Manual verification against the running backend**

With the backend on `:8000` and frontend on `:3000`, ask Cockpit (Live) a grounded question; confirm numbered citations appear and clicking one shows its content. (No unit test — this is CopilotKit UI; the E2E in Chunk 4 is the automated gate.)

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/components/console/EvidencePanel.tsx apps/frontend/styles/globals.css
git commit -m "feat(frontend): structured clickable citations in EvidencePanel (click → content)"
```

---

## Chunk 4: E2E — citations + A-vs-B ACL round-trip; Selfwiki rollout

**Depends on:** Chunks 1–3 + Chunk 2 (the stamped cockpit-kb).

**Files:**
- Modify: `e2e/smoke.spec.ts` (add a grounded-citations assertion on Cockpit Live)
- Create: `apps/backend/eval/grounded_acl_roundtrip_test.py` (the A-vs-B proof, mirrors `access_control_test.py`)
- Reference: `apps/backend/eval/access_control_test.py` (ROPC two-identity pattern)

- [ ] **Step 1: Write the A-vs-B round-trip test (infra-gated)**

Create `eval/grounded_acl_roundtrip_test.py` modeled on `access_control_test.py`: acquire ROPC tokens for `COCKPIT_TEST_USER_A` and `COCKPIT_TEST_USER_B`, run `stream_grounded_agui` (or `build_responses_kwargs` + a direct Responses call) as each for the probe query from Chunk 2, collect the returned citations, and assert **A's citations include the confidential component and B's do NOT** (spec §5: "B lacks the confidential citation that A has" — a trivial B-declines does not pass because we assert A *has* it and B *lacks that specific source*). SKIP cleanly without creds.

- [ ] **Step 2: Run it**

Run: `cd apps/backend && uv run python -m eval.grounded_acl_roundtrip_test`
Expected: `PASS` with live creds + the Chunk 2 stamp; SKIP without.

- [ ] **Step 3: Extend the Playwright smoke — Cockpit Live citations**

In `e2e/smoke.spec.ts`, after sign-in, navigate to `/d/cockpit` (Live mode, NOT the hosted toggle), send a suggested grounded prompt, and assert the FONTES panel shows at least one **numbered citation** (not the placeholder) and that clicking it reveals content. Screenshot each step (the harness's `shot()` helper).

- [ ] **Step 4: Run the E2E (infra-gated; skips without E2E_USER/E2E_PASS)**

Run: `cd e2e && npx playwright test smoke.spec.ts` (with `E2E_BASE_URL` pointing at the deployed app or local). Expected: the Cockpit-citations assertion passes; artifacts in `e2e/artifacts/steps/`.

- [ ] **Step 5: Selfwiki rollout confirmation**

Selfwiki already flows through the same `/selfwiki` router endpoint (Chunk 1) with `acl=False`. Manually (or via a smoke step) confirm Selfwiki Live answers grounded with citations and **sends no ACL header** (no permission metadata on selfwiki-kb). No re-ingest needed for Selfwiki.

- [ ] **Step 6: Commit**

```bash
git add e2e/smoke.spec.ts apps/backend/eval/grounded_acl_roundtrip_test.py
git commit -m "test(e2e): cockpit Live structured citations + A-vs-B per-user ACL round-trip"
```

---

## Final verification (before finishing the branch)

- [ ] Infra-free tests green: `cd apps/backend && uv run python -m eval.grounded_payload_test` → `PASS`.
- [ ] Import wiring valid: `uv run python -c "import app.main"`.
- [ ] Infra-gated tests run or SKIP cleanly (never fabricate): `eval.cockpit_acl_stamp_test`, `eval.grounded_acl_roundtrip_test`, `eval.step0_grounded_citations_spike`.
- [ ] self_hosted byte-identical for non-grounded domains (helpdesk workflow, platform, hosted twins untouched); shared-mode domain gate preserved on the new router endpoints.
- [ ] `docs/MICROSOFT-ALIGNMENT.md` citations row updated from ⚠️ deviation to ✅ once Chunk 4 is green (the migration shipped).
- [ ] Hand off via superpowers:finishing-a-development-branch (feature/grounded-obo-citations → develop, per Git Flow).
