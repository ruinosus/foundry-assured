---
title: Skills-driven artifact generation (+ MCP grounding) design
description: Evolve the Artifacts Studio from a fixed-prompt HTML generator into a skill-driven agent — a SkillsProvider over a library of SKILL.md artifact-type skills (slides/report/dashboard/walkthrough), the agent producing the full artifact (title+type+html) via progressive disclosure, with read-only MCP grounding to pull real data.
type: design
status: draft
updated: 2026-07-06
---

# Skills-driven artifact generation (+ MCP grounding)

## 1. Context & goal

The Artifacts Studio (shipped) generates a self-contained HTML document from a fixed system prompt;
the user still types the Title and picks the Type by hand. Two limitations: (a) the *style/type* of
HTML is baked into one prompt — adding a new kind means editing code; (b) the agent only produces the
HTML, not the surrounding metadata.

**Goal:** turn the Studio agent into a **skill-driven** generator:
- Adding an artifact *type/style* = dropping a **`SKILL.md` folder** (the open Anthropic Agent Skills
  format, natively supported by Microsoft Agent Framework), reusing community skills like
  [`frontend-slides`](https://github.com/zarazhangrui/frontend-slides).
- The agent produces the **whole artifact** — `title`, `type`, and `html` — so the creation screen is
  fully agent-driven: describe → review → save.
- The agent can optionally **ground the artifact in real data via read-only MCP** (Learn now;
  ADO/GitHub/Azure when configured), reusing the platform domain's MCP building blocks.

## 2. Background & references (verified)

- **Microsoft Agent Framework has first-class Agent Skills (Python).** Verified in the INSTALLED
  `agent-framework==1.9.0`: `from agent_framework import SkillsProvider, FileSkill, InlineSkill,
  SkillFrontmatter, InlineSkillResource`, and `SkillsProvider.from_paths(skill_paths, *,
  script_runner=None, require_script_approval=False, ...)`. `Agent.__init__` accepts both
  `context_providers=[...]` and `tools=[...]`.
  ([MS Learn — Agent Skills](https://learn.microsoft.com/en-us/agent-framework/agents/skills))
- **Progressive disclosure is native:** the provider advertises each skill (~100 tokens) in the system
  prompt and auto-registers `load_skill` / `read_skill_resource` tools (and `run_skill_script` only if a
  `script_runner` is passed). The agent pulls full `SKILL.md` + resources only when relevant.
- **The SKILL.md format is the open Anthropic Agent Skills standard** (frontmatter `name`/`description`
  + markdown body + resource files), so `frontend-slides` and other community skills drop in.
  ([anthropics/skills](https://github.com/anthropics/skills))
- **MCP building blocks already exist** (`app/agents/mcp/`, used by the `platform` domain):
  `build_mcp_tools()` returns `list[MCPStreamableHTTPTool]` filtered by the caller's role/OBO/tenant
  (`app/agents/mcp/tools.py:223`); the registry (`app/agents/mcp/registry.py`) classifies each server's
  read vs write tools; `visible_tools(server, roles)` returns `(reads, writes)`. Composes into an agent
  via `tools=[...]` (`app/agents/platform.py:43`).
- **Composability confirmed:** `tools=` (MCP tools + plain `@tool`) and `context_providers=` (providers)
  are orthogonal constructor kwargs — used independently across the repo (`platform.py`,
  `artifacts_studio.py`, `concierge.py`, `workflow/agents.py`); the SDK signature supports all three
  simultaneously.
- **CopilotKit renders the skill/tool activity** over AG-UI (the existing `useAgent`/`agent.subscribe`
  tap already sees tool calls), so "loading skill: slides" can surface as chat activity.

## 3. Scope (layered) & non-goals

This spec is **Layer 1 (skill-driven, agent-produces-everything) + Layer 2 (read-only MCP grounding)**,
per the agreed decomposition. **Out of scope (future layers / explicitly not now):**
- **Skill scripts / shell execution** — no `script_runner`; skills are model instructions only (no
  `run_skill_script`). The `frontend-slides` scripts (`extract-pptx.py`, `deploy.sh`, `export-pdf.sh`)
  are **not** vendored.
- **MCP write tools** — the artifacts agent gets **read tools only**. Creating ADO/GitHub items etc.
  stays in the `platform` domain (which has its own HITL). No external writes from artifact generation.
- **MCP Apps** (interactive third-party UI blocks) and **A2A** (agent-to-agent delegation) — Layer 3, future.
- **Per-tenant custom skill uploads** — skills ship in the repo/container for now (global).
- **Re-versioning (v2 artifacts)** — separate feature, not this one.

## 4. Architecture

```
/artifacts/new (describe-only canvas)
   │  chat + optional Skill selector (Auto | slides | report | dashboard | walkthrough)
   ▼  AG-UI
Artifacts Studio agent  (Microsoft Agent Framework, per-request)
   ├─ context_providers=[ SkillsProvider.from_paths("artifact-skills") ]   ← progressive disclosure
   │      advertises 4 skills → load_skill / read_skill_resource (reads, no scripts)
   ├─ tools=[ update_artifact(html,title,type,skill),                       ← produces the WHOLE artifact
   │          *build_artifact_mcp_reads() ]                                 ← read-only grounding (gated)
   └─ AgentFrameworkAgent(state_schema, predict_state_config, require_confirmation=True)
          streams html live + surfaces title/type/skill → frontend auto-fills
```

## 5. Backend: agent construction (`app/agents/artifacts_studio.py`)

- Switch `build_studio_agent()` from `client.as_agent(...)` to
  `Agent(client=FoundryChatClient(..., credential=credential_for_request()), instructions=_STUDIO_INSTRUCTIONS,
  context_providers=[skills_provider], tools=[update_artifact, *build_artifact_mcp_reads()])`.
  (Confirm `Agent(client=...)` behaves equivalently to `as_agent`; both are used in-repo.)
- `skills_provider = SkillsProvider.from_paths(<artifact-skills dir>)` — **no `script_runner`** (scripts disabled).
- **`update_artifact` becomes 4-arg:** `update_artifact(html: str, title: str, type: str, skill: str)`,
  keeping `@tool(approval_mode="always_require")` (the edit-confirmation still gates each version).
- **Instructions** (`_STUDIO_INSTRUCTIONS`): "Pick the skill that best matches the requested artifact; if
  the user pinned a skill, use it. Call `load_skill`/`read_skill_resource` to follow its SKILL.md. Then
  call `update_artifact` with the COMPLETE `html` (starting `<!doctype html>`, self-contained), a concise
  `title`, a `type` from {report, presentation, walkthrough, dashboard}, and the `skill` name you used.
  Use the read-only data tools only when the user asks for data-grounded content."

## 6. Skills library (`apps/backend/artifact-skills/`)

Four skill folders, Anthropic `SKILL.md` format (YAML frontmatter `name` + `description` + a `type`
category; markdown body ≤ ~500 lines; resource files loaded on demand):
- **`slides/`** — vendored + trimmed from `frontend-slides` (SKILL.md + `STYLE_PRESETS.md` +
  `viewport-base.css` + `html-template.md`; **drop** `scripts/` and the 34-pack unless needed). Category: `presentation`.
- **`report/`** — first-party: executive one-pager (header band, sections, feature cards). Category: `report`.
- **`dashboard/`** — first-party: KPI tiles + inline-SVG chart, no external libs. Category: `dashboard`.
- **`walkthrough/`** — first-party: numbered steps + callouts. Category: `walkthrough`.

Vendored `frontend-slides` content keeps its MIT/source attribution. Skills are **data** (instructions),
versioned in the repo, shipped in the backend container image, read at runtime by the provider.

## 7. Skill selection (hybrid)

- **Auto (default):** the agent chooses via progressive disclosure; the `skill` it reports in
  `update_artifact` (and/or the `load_skill` call it makes) is surfaced as `state.skill`.
- **Override:** a frontend selector — `Auto | slides | report | dashboard | walkthrough`. Picking a
  specific skill sends a hint the agent must honor (e.g. a prepended instruction / a first-message prefix
  like "Use the `slides` skill.").
- **Regenerate:** a button re-runs with the (possibly changed) skill selection.
- The UI always shows **which skill was used** (from `state.skill`).

## 8. Streaming / state — html live + title/type/skill auto-fill

The agent state grows from one field to four: `state_schema = { html, title, type, skill }` (all strings).
The **live preview** still streams `html` char-by-char (predictive `STATE_DELTA`, as today); `title`,
`type`, and `skill` populate the (editable) form fields.

> **VERIFY-LIVE (highest-risk mechanism, like the canvas approval wiring):** the exact way to surface all
> four fields is confirmed during implementation. Two candidate mechanisms: (a) **multi-field predictive** —
> `predict_state_config` maps each of the four state keys to its `update_artifact` argument, so all stream
> (html char-by-char; the short fields quickly); or (b) **html predictive + the rest from the final
> `STATE_SNAPSHOT`** (title/type/skill appear when the tool completes — fine, they need not stream). The
> plan's E2E chunk probes `/artifacts-studio` directly (as we did for the approval event) and picks the
> mechanism that actually works; the frontend reads whichever the backend populates. Keep `html`
> predictive either way.

## 9. MCP read-only grounding (`app/agents/mcp/`)

- New `build_artifact_mcp_reads()` (in `app/agents/mcp/tools.py`) mirrors `build_mcp_tools()` but builds
  each `MCPStreamableHTTPTool` with **only the server's `reads`** as `allowed_tools` (drop `writes`). Same
  role/OBO/tenant filtering, same `MCP_ENABLED` gate. Returns `[]` when MCP is off (default).
- Composed into the Studio agent's `tools=[...]`. The model calls a read tool only when the user asks for
  data-grounded content; a skill may instruct it (e.g., a future "release-notes" skill).
- **Only `learn` is live out-of-the-box**; ADO/GitHub/Azure light up when their config/Connection exists.
  This is acceptable — MCP grounding degrades gracefully (no tools → the agent just generates from the prompt).

## 10. Data model

- `ArtifactRecord` gains **`skill: str | None`** (the recipe used; nullable for legacy/create-from-html).
- `ALLOWED_TYPES` += **`dashboard`** → `{report, presentation, walkthrough, dashboard}`. `create_draft`
  still validates `type`. The `POST /artifacts/html` create-from-html body gains optional `skill`.
- The `_dto` + list/detail surfaces show the skill.

## 11. Frontend reshape (`components/artifacts/ArtifactStudio.tsx`)

- Remove the manual Title/Type inputs from the top; instead:
  - A **Skill selector** (`Auto | slides | report | dashboard | walkthrough`) + a **Regenerate** button.
  - **Title / Type / Skill** become **auto-filled, editable** fields, populated from `state.title/type/skill`.
- Live `html` preview unchanged (`LivePreview`, sandbox `allow-scripts`).
- Edit-approval card unchanged.
- **Save as draft** posts `{ title, type, html, skill }` to `/api/artifacts/create`.
- Skill-loading activity ("loading skill: slides") may render from the tool-call stream (nice-to-have).

## 12. Security

- Skills are **instructions to the model**, not executable code; **no `script_runner`** → zero shell.
- MCP tools are **read-only** and role/OBO-gated; no external writes.
- Preview sandbox unchanged (`allow-scripts`, no `allow-same-origin`); `update_artifact` keeps
  `approval_mode="always_require"`; generated HTML re-validated on save.
- Skills ship in the repo (reviewed), not user-uploaded.

## 13. Testing

**Backend (runner-style `*_test.py`, `uv run python -m eval.<name>`):**
- Skills discovery: `SkillsProvider.from_paths(<artifact-skills>)` finds the 4 skills (names/descriptions);
  each folder has a valid `SKILL.md` frontmatter.
- `update_artifact` is a 4-arg `FunctionTool`; `state_schema`/`predict_state_config` reference `html`
  (+ the chosen mechanism's fields).
- `build_artifact_mcp_reads()`: with a faked registry/roles, returns tools whose `allowed_tools` contain
  **no** write tool names; returns `[]` when `MCP_ENABLED` is off.
- `create_draft` accepts + stores `skill`; `dashboard` is a valid type.

**E2E (Playwright, local auth-off):** extend `e2e/artifacts-studio.spec.ts` (or a new spec):
describe → agent auto-picks a skill → `html` streams live + Title/Type/Skill auto-fill → approve → save →
detail draft shows the skill. A second case: pin the **`slides`** skill in the selector → regenerate →
the used skill is `slides`. (This is where the multi-field surfacing mechanism is verified live.)

## 14. File structure (create / modify)

**Backend:**
- Create `apps/backend/artifact-skills/{slides,report,dashboard,walkthrough}/SKILL.md` (+ slides resources).
- Modify `app/agents/artifacts_studio.py` — `Agent(...)` with `context_providers=[SkillsProvider…]`,
  4-arg `update_artifact`, MCP reads, new instructions, expanded `state_schema`/`predict_state_config`.
- Modify `app/agents/mcp/tools.py` — add `build_artifact_mcp_reads()`.
- Modify `app/services/artifacts.py` — `ALLOWED_TYPES` += `dashboard`; `create_draft` accepts `skill`.
- Modify `app/artifacts/models.py` — `ArtifactRecord.skill` + store (de)serialization.
- Modify `app/api/artifacts.py` — `CreateBody.skill`; `_dto` includes skill.
- Modify `eval/artifact_studio_test.py` + `eval/artifact_service_test.py` + a new `eval/artifact_skills_test.py`.

**Frontend:**
- Modify `components/artifacts/ArtifactStudio.tsx` — skill selector + regenerate + auto-filled fields;
  read `state.title/type/skill`; save with `skill`.
- Modify `components/artifacts/ArtifactsView.tsx` / `ArtifactDetail.tsx` — show `skill` (minor).

**E2E:** extend/add the Playwright spec.

## 15. Risks & open questions

- **Multi-field predictive streaming (highest risk)** — see §8 VERIFY-LIVE. Mitigation: html stays
  predictive; title/type/skill fall back to the snapshot if per-field deltas don't stream cleanly.
- **`Agent(client=...)` vs `as_agent(...)`** — confirm equivalence for FoundryChatClient during
  implementation (both patterns exist in-repo).
- **Skill instruction discipline** — the model must always call `update_artifact` with a valid `type`
  from the enum; instructions + `create_draft` validation enforce it (invalid → 422, UI normalizes).
- **Vendoring `frontend-slides`** — trim to the HTML-generation parts (no scripts); keep attribution;
  watch the SKILL.md size (≤ ~500 lines, resources on demand).
- **MCP coverage** — only `learn` live OOTB; the feature degrades gracefully when servers aren't configured.

## 16. Roadmap (after this)

- **Layer 3:** MCP Apps (auto-rendered interactive UI via `MCPAppsMiddleware`), A2A (delegate to a
  chart/data agent). Re-versioning (v2 artifacts) as its own feature.
