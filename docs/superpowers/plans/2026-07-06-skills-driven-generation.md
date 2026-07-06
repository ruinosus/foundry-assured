# Skills-driven Artifact Generation Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Evolve the Artifacts Studio into a skill-driven agent: a `SkillsProvider` over a library of `SKILL.md` artifact-type skills (slides/report/dashboard/walkthrough), the agent producing the whole artifact (title+type+html+skill) via progressive disclosure, with a hybrid skill selector and read-only MCP grounding.

**Architecture:** The `artifacts-studio` agent gains `context_providers=[SkillsProvider.from_paths("artifact-skills")]` (native Agent Skills, Anthropic SKILL.md format) and `tools=[update_artifact, *build_artifact_mcp_reads()]`. `update_artifact` grows to produce `html`(streamed) + `title`/`type`/`skill`. The creation screen becomes describe-only: chat + a skill selector; Title/Type/Skill auto-fill from agent state; live sandbox preview + edit-approval unchanged.

**Tech Stack:** `agent-framework==1.9.0` (`SkillsProvider.from_paths`, `FoundryChatClient.as_agent`, `@tool`) · `agent-framework-ag-ui==1.0.0rc5` · MCP (`build_mcp_tools`/`MCPStreamableHTTPTool`) · FastAPI · Next.js 16 / CopilotKit v2 · Playwright.

**Spec:** `docs/superpowers/specs/2026-07-06-skills-driven-generation-design.md` (read it — this plan implements it).

**Verified (installed):** `agent_framework.SkillsProvider.from_paths(skill_paths, *, script_runner=None, require_script_approval=False, ...)`; `FoundryChatClient.as_agent(context_providers=[...], tools=[...])`; `build_mcp_tools()`/`visible_tools(server,roles)->(reads,writes)` real; `settings.mcp_enabled` default `False` and NOT checked inside `build_mcp_tools()`. `SkillsProvider` is **Experimental** — pin behavior against the installed pkg, don't rely on unverified surface (CLAUDE.md rule #1).

---

## Ground rules

- **Work from** `/Users/jefferson.barnabe/projects/foundry-helpdesk/.worktrees/html-artifacts` (branch `feature/html-artifacts`).
- **No pytest.** Backend tests are `main() -> int` modules run with `uv run python -m eval.<name>` from `apps/backend/`. The `VIRTUAL_ENV … does not match` warning is harmless.
- **Frontend: no unit harness** — verify with `npx tsc --noEmit` + `npm run build` + Playwright.
- **Commit per task** with the given message + trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Do NOT amend earlier commits. Never stage `apps/frontend/{package-lock.json,tsconfig.json,next-env.d.ts}` (dev-server churn).
- Local dev servers may run (backend `:8010` `--reload` auth-off `ARTIFACT_STORE_BACKEND=memory`; frontend `:3010`) — hot-reload picks up edits; don't restart them.
- **CLAUDE.md rule #1:** all SDK surfaces are copied from real files (cited). If something drifts, mirror the real file — don't invent. `SkillsProvider` is Experimental → verify at implementation.

---

## File structure

**Backend (`apps/backend/`):**
- Create `artifact-skills/{slides,report,dashboard,walkthrough}/SKILL.md` (+ `slides/` resources vendored from frontend-slides).
- Modify `app/artifacts/models.py` — `ArtifactRecord.skill` + `ALLOWED_TYPES += dashboard`.
- Modify `app/artifacts/store.py` — `skill` in `_FIELDS` + `_record_from_entity`.
- Modify `app/services/artifacts.py` — `create_draft` accepts+stores `skill`; `generate()` passes it.
- Modify `app/api/artifacts.py` — `CreateBody.skill`, `_dto` includes `skill`.
- Modify `app/agents/mcp/tools.py` — add `build_artifact_mcp_reads()`.
- Modify `app/agents/artifacts_studio.py` — `SkillsProvider` context provider, 4-arg `update_artifact`, expanded `state_schema`/`predict_state_config`, MCP reads, instructions.
- Modify `eval/artifact_service_test.py`; create `eval/artifact_skills_test.py`; extend `eval/artifact_studio_test.py`.

**Frontend (`apps/frontend/`):**
- Modify `components/artifacts/ArtifactStudio.tsx` — skill selector + regenerate; auto-fill Title/Type/Skill from state; save `skill`.
- Modify `components/artifacts/ArtifactsView.tsx` + `ArtifactDetail.tsx` — show `skill`.

**E2E:** extend `e2e/artifacts-studio.spec.ts`.

---

## Chunk 1: Data model — the `skill` field end-to-end + `dashboard` type

### Task 1: `ArtifactRecord.skill` + `dashboard` type + store/service/API

**Files:** Modify `app/artifacts/models.py`, `app/artifacts/store.py`, `app/services/artifacts.py`, `app/api/artifacts.py`; extend `eval/artifact_service_test.py`.

- [ ] **Step 1: Extend `eval/artifact_service_test.py`** — after the existing create_draft checks, add:

```python
    # skill field round-trips + dashboard is a valid type
    rskill = svc.create_draft(
        tenant_id="t1", title="S", description="", type="dashboard",
        html="<html><body>ok</body></html>", user=U(), skill="dashboard",
    )
    check("dashboard type accepted", rskill.type == "dashboard")
    check("skill stored on record", rskill.skill == "dashboard")
    got = svc.get_artifact("t1", rskill.id, user=U())
    check("skill round-trips via store", got.skill == "dashboard")
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: FAIL — `create_draft() got an unexpected keyword argument 'skill'` (and/or `dashboard` rejected).

- [ ] **Step 3a: `app/artifacts/models.py`** — add `dashboard` to the type constants + `ALLOWED_TYPES`, and add `skill` to the frozen dataclass (optional field, after `content_hash`):

```python
class ArtifactType:
    PRESENTATION = "presentation"
    REPORT = "report"
    WALKTHROUGH = "walkthrough"
    DASHBOARD = "dashboard"


ALLOWED_TYPES = frozenset(
    {ArtifactType.PRESENTATION, ArtifactType.REPORT, ArtifactType.WALKTHROUGH, ArtifactType.DASHBOARD}
)
```
and in `ArtifactRecord` (append after `content_hash: str | None = None`):
```python
    skill: str | None = None
```

- [ ] **Step 3b: `app/artifacts/store.py`** — add `"skill"` to `_FIELDS` and read it in `_record_from_entity`:

```python
_FIELDS = (
    "title", "description", "type", "status", "created_by", "created_at",
    "updated_at", "blob_path", "version", "approved_by", "approved_at",
    "content_hash", "skill",
)
```
and in `_record_from_entity`, before the closing `)`:
```python
        skill=e.get("skill") or None,
```

- [ ] **Step 3c: `app/services/artifacts.py`** — add `skill` param to `create_draft` (keyword-only, default None) and set it on the record:

```python
def create_draft(*, tenant_id: str, title: str, description: str, type: str,
                 html: str, user, skill: str | None = None) -> ArtifactRecord:
```
and in the `ArtifactRecord(...)` construction add `skill=skill,`. (The `generate()` caller still works — it just won't pass skill; leave it, or pass `skill=None`.)

- [ ] **Step 3d: `app/api/artifacts.py`** — `CreateBody` gains `skill`, `create_route` passes it, `_dto` returns it:

```python
class CreateBody(BaseModel):
    title: str
    description: str = ""
    type: str = "report"
    html: str
    skill: str | None = None
```
`create_route`: add `skill=body.skill` to the `svc.create_draft(...)` call.
`_dto`: add `"skill": rec.skill,` to the returned dict.

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test && uv run python -m eval.artifact_store_test && uv run python -m eval.artifact_rbac_test && uv run python -m eval.artifact_studio_test`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/artifacts/models.py apps/backend/app/artifacts/store.py apps/backend/app/services/artifacts.py apps/backend/app/api/artifacts.py apps/backend/eval/artifact_service_test.py
git commit -m "feat(artifacts): add skill field end-to-end + dashboard type"
```

---

## Chunk 2: Skills library (`apps/backend/artifact-skills/`)

### Task 2: The four SKILL.md skills + discovery test

**Files:** Create `apps/backend/artifact-skills/{slides,report,dashboard,walkthrough}/SKILL.md` (+ slides resources); create `apps/backend/eval/artifact_skills_test.py`.

Format: Anthropic Agent Skills `SKILL.md` — YAML frontmatter (`name`, `description`) + markdown body. Add a `type:` frontmatter key so the agent knows the category (report/presentation/walkthrough/dashboard). Keep each SKILL.md ≤ ~500 lines; move long reference to resource files loaded on demand.

- [ ] **Step 1: Write the failing test** (`eval/artifact_skills_test.py`):

```python
"""Artifact skills discovery — the SkillsProvider finds the 4 skills.

Run (from apps/backend/):  uv run python -m eval.artifact_skills_test
"""
import sys
from pathlib import Path


def main() -> int:
    failures: list[str] = []

    def check(name, cond):
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    skills_dir = Path(__file__).resolve().parents[1] / "artifact-skills"
    check("artifact-skills dir exists", skills_dir.is_dir())

    expected = {"slides", "report", "dashboard", "walkthrough"}
    found = {p.parent.name for p in skills_dir.glob("*/SKILL.md")}
    check(f"4 SKILL.md skills present ({expected})", expected <= found)

    # Each SKILL.md has YAML frontmatter with name + description + a valid type.
    from app.artifacts.models import ALLOWED_TYPES
    for name in expected:
        text = (skills_dir / name / "SKILL.md").read_text(encoding="utf-8")
        check(f"{name}: has frontmatter", text.startswith("---"))
        check(f"{name}: declares name", "name:" in text.split("---")[1])
        check(f"{name}: declares a valid type", any(f"type: {t}" in text for t in ALLOWED_TYPES))

    # SkillsProvider discovers them (Experimental API — verify it imports + from_paths works).
    from agent_framework import SkillsProvider
    provider = SkillsProvider.from_paths(str(skills_dir))
    check("SkillsProvider.from_paths constructs", provider is not None)

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_skills_test`
Expected: FAIL — `artifact-skills dir exists` false.

- [ ] **Step 3: Author the four skills.** Each `SKILL.md`: frontmatter `name`, `description`, `type`; body = concise generation guidance producing a **single self-contained HTML document** (inline CSS/JS, no external requests, starts `<!doctype html>`), safe for a sandboxed iframe.
  - `report/SKILL.md` (type: report) — executive one-pager: header band, sections, feature cards, footer.
  - `dashboard/SKILL.md` (type: dashboard) — KPI tiles row + an inline `<svg>` bar chart (NO external libs).
  - `walkthrough/SKILL.md` (type: walkthrough) — numbered step cards + a highlighted callout.
  - `slides/` — **vendor + trim** [`frontend-slides`](https://github.com/zarazhangrui/frontend-slides): copy `SKILL.md` (type: presentation) + the HTML-generation resources it references (`STYLE_PRESETS.md`, `viewport-base.css`, `html-template.md`). **DROP** `scripts/` (extract-pptx/deploy/export-pdf) and the 34-template pack (or include a trimmed subset). Preserve the source's LICENSE/attribution (add a short `VENDORED.md` noting origin + MIT). Ensure the `SKILL.md` frontmatter has `type: presentation` and instructs "return ONE self-contained HTML file".

> Keep skills as **instructions** (no scripts). The provider is attached with **no `script_runner`** (Task 4), so `run_skill_script` will be visible but safely no-op.

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_skills_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/artifact-skills apps/backend/eval/artifact_skills_test.py
git commit -m "feat(artifacts): artifact-skills library (slides/report/dashboard/walkthrough) + discovery test"
```

---

## Chunk 3: Backend agent — SkillsProvider + 4-arg tool + MCP reads (HIGHEST RISK)

### Task 3: `build_artifact_mcp_reads()` (read-only, mcp_enabled-gated)

**Files:** Modify `app/agents/mcp/tools.py`; create `eval/artifact_mcp_reads_test.py`.

Mirror `_build_one` (`tools.py:82-109`) but allow **only reads** and add the `mcp_enabled` gate (`build_mcp_tools()` does NOT check it — verified).

- [ ] **Step 1: Write the failing test** (`eval/artifact_mcp_reads_test.py`):

```python
"""build_artifact_mcp_reads: read-only + mcp_enabled gate (no network).

Run (from apps/backend/):  uv run python -m eval.artifact_mcp_reads_test
"""
import sys


def main() -> int:
    failures: list[str] = []

    def check(name, cond):
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    import app.core.settings as settings_mod
    from app.agents.mcp import tools as mcp_tools

    # Gate: off by default → no tools.
    settings_mod.settings.mcp_enabled = False
    check("returns [] when MCP disabled", mcp_tools.build_artifact_mcp_reads() == [])

    # Enabled → tools built, and NONE expose a write tool name (read-only).
    settings_mod.settings.mcp_enabled = True
    from app.agents.mcp.registry import enabled_servers
    write_names = {w for s in enabled_servers() for w in s.write_tools}
    built = mcp_tools.build_artifact_mcp_reads()
    check("builds at least one read tool when enabled (learn is public)", len(built) >= 1)
    exposed = {t for tool in built for t in getattr(tool, "allowed_tools", [])}
    check("no write tools exposed", not (exposed & write_names))
    settings_mod.settings.mcp_enabled = False  # restore

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_mcp_reads_test`
Expected: FAIL — `module 'app.agents.mcp.tools' has no attribute 'build_artifact_mcp_reads'`.

- [ ] **Step 3: Add `build_artifact_mcp_reads()`** to `app/agents/mcp/tools.py` (mirror `_build_one`, reads-only, gated):

```python
def _build_one_read_only(server: McpServer, roles: set[str]) -> MCPStreamableHTTPTool | None:
    reads, _writes = visible_tools(server, roles)
    if not reads:
        return None
    url = _resolve_url(server)
    if not url:
        return None
    kwargs: dict = {
        "name": f"mcp_{server.id}",
        "url": url,
        "allowed_tools": reads,            # READ tools only — never writes
        "approval_mode": "never_require",
    }
    if server.auth == "public":
        pass
    elif server.auth == "obo" and server.obo_scope:
        kwargs["header_provider"] = _obo_header_provider(server.obo_scope)
    elif server.auth == "github_pat":
        pat = tenant_config().mcp_github_pat
        if not pat:
            return None
        kwargs["header_provider"] = _static_header_provider(pat)
    else:
        return None
    return MCPStreamableHTTPTool(**kwargs)


def build_artifact_mcp_reads() -> list[MCPStreamableHTTPTool]:
    """Read-only MCP tools for grounding artifact generation. Unlike build_mcp_tools(), this gates
    on settings.mcp_enabled itself (that gate normally lives in the caller, platform_configured())
    and drops ALL write tools — artifact generation must never write to external systems."""
    if not settings.mcp_enabled:
        return []
    roles = current_roles() if settings.auth_enabled else {"Admin"}
    if settings.deployment_mode == "shared":
        # Reuse the connection path but keep reads only: filter each built tool is overkill; simplest
        # is to build via the self-hosted read-only path over enabled_servers when a shared MCP story
        # isn't needed for artifacts yet. Keep parity with build_mcp_tools's shared branch ONLY if
        # artifacts need per-tenant MCP; for the MVP, self-hosted registry path is sufficient.
        tools = [_build_one_read_only(s, roles) for s in enabled_servers()]
        return [t for t in tools if t is not None]
    tools = [_build_one_read_only(s, roles) for s in enabled_servers()]
    return [t for t in tools if t is not None]
```

> NOTE: the shared-vs-self_hosted branch is collapsed for the MVP (artifacts use the registry read path in both). If per-tenant MCP Connections are wanted for artifacts later, mirror `build_from_connections` reads-only. Confirm this simplification is acceptable during review; it does not expose writes either way.

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_mcp_reads_test`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/agents/mcp/tools.py apps/backend/eval/artifact_mcp_reads_test.py
git commit -m "feat(artifacts): build_artifact_mcp_reads — read-only, mcp_enabled-gated MCP grounding"
```

---

### Task 4: SkillsProvider + 4-arg `update_artifact` + expanded state (VERIFY-LIVE)

**Files:** Modify `app/agents/artifacts_studio.py`; extend `eval/artifact_studio_test.py`.

The agent gains skills (context provider) + MCP reads (tools) and produces the whole artifact. The **multi-field streaming mechanism is verified live** (like the approval wiring) in Step 4b before finalizing.

- [ ] **Step 1: Extend `eval/artifact_studio_test.py`** — assert the tool now takes 4 args and the provider/tools are wired:

```python
    import inspect as _inspect
    params = list(_inspect.signature(update_artifact.func if hasattr(update_artifact, "func") else update_artifact).parameters) \
        if False else None  # NOTE: FunctionTool wraps the fn; assert via its schema instead
    # The FunctionTool exposes its parameter names; assert html/title/type/skill are all present.
    schema_params = set(getattr(update_artifact, "parameters", {}) or {})
    # Fallback: check the underlying callable if the schema isn't introspectable.
    check("update_artifact takes html/title/type/skill",
          {"html", "title", "type", "skill"} <= (schema_params or set(
              _inspect.signature(getattr(update_artifact, "_func", lambda html, title, type, skill: None)).parameters)))
```
> The exact way to read a `FunctionTool`'s parameter names varies — during implementation, print `dir(update_artifact)` / its schema and assert the four names robustly (mirror how `artifact_studio_test.py` already does the tolerant `FunctionTool` check).

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_studio_test`
Expected: FAIL (tool has only `html`).

- [ ] **Step 3: Update `app/agents/artifacts_studio.py`:**
  - `update_artifact` → 4 args, keep `@tool(approval_mode="always_require")`:
    ```python
    @tool(approval_mode="always_require")
    def update_artifact(html: str, title: str, type: str, skill: str) -> str:
        """Write the COMPLETE artifact: the full HTML document (html), a concise title, a type
        (one of report|presentation|walkthrough|dashboard), and the skill name you used."""
        return "Artifact updated."
    ```
  - `_STUDIO_INSTRUCTIONS` → add skill guidance: "Choose the skill that best matches the requested artifact; if the user pinned a skill, use it. Follow its SKILL.md via load_skill/read_skill_resource. Call `update_artifact` with the complete `html`, a concise `title`, a `type` from {report,presentation,walkthrough,dashboard}, and the `skill` you used. Use the read-only data tools only when the user asks for data-grounded content."
  - `build_studio_agent()` → add the provider + MCP reads:
    ```python
    from pathlib import Path
    from agent_framework import SkillsProvider
    from app.agents.mcp.tools import build_artifact_mcp_reads

    _SKILLS_DIR = Path(__file__).resolve().parents[2] / "artifact-skills"   # apps/backend/artifact-skills

    def build_studio_agent():
        cfg = tenant_config()
        client = FoundryChatClient(project_endpoint=cfg.foundry_project_endpoint or None,
                                   model=cfg.foundry_model, credential=credential_for_request())
        return client.as_agent(
            name="ArtifactsStudio",
            description="Conversationally generates and refines a self-contained HTML artifact.",
            instructions=_STUDIO_INSTRUCTIONS,
            context_providers=[SkillsProvider.from_paths(str(_SKILLS_DIR))],   # no script_runner (no shell)
            tools=[update_artifact, *build_artifact_mcp_reads()],
        )
    ```
  - `state_schema` / `predict_state_config` → **provisional** (finalized in Step 4b): start with `html` predictive + the other three as state fields:
    ```python
    state_schema={
        "html": {"type": "string", "description": "The current HTML artifact document"},
        "title": {"type": "string", "description": "Concise artifact title"},
        "type": {"type": "string", "description": "report|presentation|walkthrough|dashboard"},
        "skill": {"type": "string", "description": "The skill used to generate it"},
    },
    predict_state_config={"html": {"tool": "update_artifact", "tool_argument": "html"}},
    ```

- [ ] **Step 3b: Run the studio + service + skills + mcp tests**

Run: `cd apps/backend && uv run python -m eval.artifact_studio_test && uv run python -m eval.artifact_skills_test && uv run python -m eval.artifact_mcp_reads_test && uv run python -m eval.artifact_service_test`
Expected: all PASS.

- [ ] **Step 4b: VERIFY-LIVE the multi-field surfacing** — with the local backend running (`:8010`, `--reload`, auth off, `ARTIFACT_STORE_BACKEND=memory`), probe `/artifacts-studio` directly (reuse/adapt `scratchpad/probe_studio.py` from the canvas build) sending a "make a report titled X" message, and inspect the SSE events for how `title`/`type`/`skill` arrive:
  - If they appear in `STATE_SNAPSHOT.snapshot` (and/or `STATE_DELTA` on `/title` etc.) → the state-schema approach works; keep it. Add them to `predict_state_config` too if you want them to stream.
  - If they do NOT surface in state (only `html` does) → read `title`/`type`/`skill` from the `function_approval_request` event's `value.function_call.arguments` (which carries ALL tool args) in the frontend instead. Document which mechanism won in a code comment (mirror the canvas `VERIFIED LIVE` note).
  Record the finding; the frontend (Chunk 4) consumes whichever the backend populates.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/agents/artifacts_studio.py apps/backend/eval/artifact_studio_test.py
git commit -m "feat(artifacts): studio agent is skill-driven — SkillsProvider + 4-arg update_artifact + MCP reads"
```

---

## Chunk 4: Frontend — skill selector, auto-fill, save skill

### Task 5: Reshape `ArtifactStudio.tsx`

**Files:** Modify `apps/frontend/components/artifacts/ArtifactStudio.tsx`.

Read the file first. Apply per the Chunk-3 Step-4b finding (state fields vs approval-event args).

- [ ] **Step 1: Add the skill list + state + selector.**
  - Constants: `const SKILLS = ["auto", "slides", "report", "dashboard", "walkthrough"] as const;` and extend `ARTIFACT_TYPES` to include `"dashboard"`.
  - State: add `const [skill, setSkill] = useState<string>("auto");` and `const [usedSkill, setUsedSkill] = useState<string>("");`.
  - **Auto-fill from agent state:** extend the `agent.subscribe` tap — mirror `htmlFromSnapshot`/`htmlFromDelta` to also read `snap.title`/`snap.type`/`snap.skill` (and `/title`,`/type`,`/skill` delta ops), calling `setTitle`/`setType`/`setUsedSkill` (only when the field is non-empty, so the user's manual edits aren't clobbered — track a "user touched title" ref if needed). **OR**, per Step-4b, read title/type/skill from the approval event's `function_call.arguments` in `onEvent` and set them there.
  - **Selector UI:** replace the manual Title/Type block's `<select>` for Type with a **Skill selector** (`Auto | slides | report | dashboard | walkthrough`) bound to `skill`/`setSkill`, plus a **Regenerate** button. Keep the Title `<input>` (now auto-filled + editable) and keep a Type display (auto-filled). Show `usedSkill` ("Generated with: {usedSkill}").
  - **Pin a skill:** when `skill !== "auto"`, Regenerate/send should tell the agent to use it. Simplest: prepend a system-ish hint to the next chat turn, e.g. programmatically send a message via the agent or instruct the user; for MVP, a **Regenerate** button can call `agent.runAgent(...)` with a message like `Use the ${skill} skill and regenerate.` (verify the v2 `runAgent`/message API during implementation; fall back to a prefilled chat send).
  - **Save:** add `skill: usedSkill || (skill === "auto" ? undefined : skill)` to the `save()` POST body.

- [ ] **Step 2: Verify typecheck + build**

Run: `cd apps/frontend && npx tsc --noEmit && npm run build`
Expected: clean. If build rewrites `tsconfig.json`/`next-env.d.ts`, `git checkout --` them (don't commit).

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/components/artifacts/ArtifactStudio.tsx
git commit -m "feat(artifacts): studio — skill selector + agent-filled title/type + save skill"
```

---

### Task 6: Show `skill` in list + detail

**Files:** Modify `components/artifacts/ArtifactsView.tsx`, `components/artifacts/ArtifactDetail.tsx`.

- [ ] **Step 1:** Add `skill?: string | null` to both `Artifact` types. In `ArtifactsView` add a "Skill" column (header + `<td>{a.skill ?? "—"}</td>`). In `ArtifactDetail`'s metadata pill row, add `{a.skill && <span className="muted">· {a.skill}</span>}`.
- [ ] **Step 2:** `cd apps/frontend && npx tsc --noEmit` — clean.
- [ ] **Step 3: Commit**

```bash
git add apps/frontend/components/artifacts/ArtifactsView.tsx apps/frontend/components/artifacts/ArtifactDetail.tsx
git commit -m "feat(artifacts): surface skill in list + detail"
```

---

## Chunk 5: E2E + verification

### Task 7: Playwright — skill-driven generation + override

**Files:** Modify `e2e/artifacts-studio.spec.ts`.

- [ ] **Step 1: Extend/adjust the studio E2E** for the reshaped flow:
  - Case A (auto): describe "make a slide deck about the Foundry platform" → `html` streams into the sandbox → Title/Type/Skill **auto-fill** (assert the Title input is non-empty and a "Generated with" indicator shows a skill) → approve → Save → detail draft shows the skill.
  - Case B (override): set the Skill selector to **`slides`** → Regenerate → assert the used skill is `slides`.
  - Keep the sandbox assertion (`iframe[title="artifact-preview"]` has `sandbox="allow-scripts"`).
  - Account for the "partial-head → jump-to-complete" preview behavior (§8 of the spec) — assert the FINAL rendered html (post-approval), not intermediate frames.

- [ ] **Step 2: Run it** (servers on `:3010`/`:8010`, auth off):

Run: `cd e2e && E2E_BASE_URL=http://localhost:3010 npx playwright test artifacts-studio.spec.ts --reporter=list`
Expected: pass. If the auto-fill/selector selectors differ, adjust to the real DOM; if the pin-skill mechanism doesn't take, capture the run and fix Task 5's regenerate wiring (verify-live).

- [ ] **Step 3: Commit**

```bash
git add e2e/artifacts-studio.spec.ts
git commit -m "test(artifacts): E2E — skill-driven generation + skill override"
```

---

### Task 8: Full verification + CI

- [ ] Backend suite: `cd apps/backend && uv run python -m eval.artifact_store_test && uv run python -m eval.artifact_service_test && uv run python -m eval.artifact_rbac_test && uv run python -m eval.artifact_studio_test && uv run python -m eval.artifact_skills_test && uv run python -m eval.artifact_mcp_reads_test` — all PASS.
- [ ] Wire the two new eval modules (`artifact_skills_test`, `artifact_mcp_reads_test`) into `.github/workflows/ci.yml`'s artifact-tests step. Commit.
- [ ] Frontend: `cd apps/frontend && npx tsc --noEmit && npm run build` clean; `tsconfig.json`/`next-env.d.ts` reverted.
- [ ] Both artifact E2Es green (`artifacts.spec.ts` + `artifacts-studio.spec.ts`).
- [ ] Manual smoke (@verify/@run): `/artifacts/new` → describe → skill auto-picked → Title/Type/Skill auto-fill → approve → Save → detail shows skill. Then set selector to `slides` → Regenerate → used skill = slides.
- [ ] Security review: `@security-review` (skills-as-instructions, MCP read-only, no `script_runner`, sandbox unchanged).

---

## Definition of done

- [ ] `skill` field end-to-end (model/store/service/API/DTO/frontend) + `dashboard` type; all backend eval modules green + in CI.
- [ ] 4 skills discoverable by `SkillsProvider.from_paths`; `slides` vendored from frontend-slides (no scripts, attribution kept).
- [ ] Studio agent is skill-driven (`context_providers=[SkillsProvider]`, `tools=[update_artifact, *build_artifact_mcp_reads()]`), produces title/type/skill+html; the multi-field surfacing mechanism is verified live and documented.
- [ ] MCP grounding is read-only + `MCP_ENABLED`-gated (off by default; no write tools exposed).
- [ ] Creation screen is describe-only with a working skill selector (Auto + 4) + regenerate + "generated with" indicator; Title/Type auto-filled.
- [ ] Studio + lifecycle E2Es green; sandbox invariant intact.

## Notes for the executor

- **`SkillsProvider` is Experimental** — verify its API against the installed `agent-framework 1.9.0` at implementation; if `from_paths` or `context_providers` behavior differs, adjust and report (don't invent).
- **Multi-field streaming is the highest-risk item** (Task 4 Step 4b): html stays predictive ("partial-head → jump-to-complete", per spec §8 — not a regression); title/type/skill surface via state OR the approval-event arguments — pick what the live probe shows works, exactly as the canvas approval wiring was nailed live.
- **MCP degrades gracefully** — only `learn` is live OOTB; with `MCP_ENABLED` off (default) the agent just generates from skills. Don't block on ADO/GitHub/Azure.
- **No shell** — attach `SkillsProvider` with no `script_runner`; `run_skill_script` is visible but safely errors.
