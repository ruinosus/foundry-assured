# Artifacts Studio — Canvas Redesign (Design)

- **Status:** Draft
- **Date:** 2026-07-07
- **Area:** `apps/frontend` (artifacts feature), no backend change
- **Related:** builds on the HTML Artifacts feature (PR #101); the Studio agent lives at
  `apps/backend/app/agents/artifacts_studio.py` (unchanged here)

## Context & problem

The Artifacts Studio ships as a two-pane screen (chat left, preview + controls right). Manual
testing surfaced a real UX defect: the chat renders CopilotKit's **default tool-call cards**, and
the tools that go through the HITL approval flow — `update_artifact` (`approval_mode="always_require"`)
and the framework's `confirm_changes` pseudo-tool — **never receive a terminal status event**, so
their cards stay stuck on **"Running"** forever. Meanwhile the *real* approval control ("Apply this
version? → Approve / Reject") already lives in the right panel. The result is **duplication**: the
chat shows a broken, redundant echo of an approval the panel already handles well.

The root cause is upstream: the `agent-framework-ag-ui` adapter does not emit a terminal
tool-call-end for HITL-gated tools (the interrupt pauses the run; the post-approval result arrives
in a segment CopilotKit does not correlate to the original card). Patching the adapter is fragile and
would violate the "don't invent SDK signatures" rule. The fix belongs in the frontend: **take control
of tool-call rendering** and, while we're there, **redesign the Studio around the artifact** instead
of bolting a chat next to a form.

Research (CopilotKit generative-UI guide, AG-UI HITL docs, Chainlit-style inline tool visualization)
converges on two principles: (1) showing *what a tool does and what inputs it received* builds trust —
so we surface tool activity, we don't hide it; (2) an approval is **first-class generative UI** that
shows the tool name + arguments at the decision point. The chosen direction ("Canvas") makes the
**artifact the hero**, with tool activity as a compact steps strip and approval as a review bar over
the preview.

## Goals

- Kill the stuck-"Running" cards and the approval duplication.
- Surface tool activity honestly: which skill was chosen, what `update_artifact` received.
- Make the artifact the visual center (v0 / Claude-Artifacts feel), for **both** the Studio
  (create/edit) and the published-artifact **detail** page, sharing one "canvas" visual language.
- Keep the HITL review gate (per-version Approve/Reject) — it is the safety mechanism and is already
  verified end-to-end.
- Zero backend change; reuse the existing streaming, approval-resume, and save logic.

## Non-goals

- No change to `update_artifact`'s `approval_mode` (the review gate stays).
- No change to the backend agent, routes, store, skills, or MCP wiring.
- No redesign of the artifacts **list** page (`ArtifactsView.tsx`) beyond what falls out naturally.
- No new artifact types or generation behavior.

## Foundation (Studio only): hide internal tool cards + a self-rendered steps strip

Two mechanisms, with a clear division of responsibility — this is the key architectural decision:

**(a) `renderToolCalls` = suppress the internal tools *inside the chat transcript*.** CopilotKit v2
renders tool calls inline in `<CopilotChat>`'s transcript, driven by `renderToolCalls?:
ReactToolCallRenderer<any>[]` on **`CopilotKitProvider`** (the `Studio` component already wraps
`<StudioCanvas/>` in `<CopilotKitProvider runtimeUrl="/api/copilotkit">` — the prop goes there, not
on `<CopilotChat>`). We register **hide** renderers (`render: () => <></>`) for the internal tools so
the chat rail stays pure conversation and the stuck "Running" cards disappear:
`confirm_changes`, `update_artifact`, and the SkillsProvider tool(s) (`load_skill` /
`read_skill_resource` / `run_skill_script`). Build entries with `defineToolCallRenderer` /
`useRenderTool`; the render signature is `{ name, toolCallId, args, status, result }`,
`status ∈ { InProgress, Executing, Complete }`.

> **Critical:** hiding a tool's *transcript render* does **not** suppress the AG-UI interrupt event.
> The approval is captured in `onEvent` (`function_approval_request` / `request_info`) which sets
> `pending`; that path is independent of `renderToolCalls`. So the review bar keeps working even
> though `confirm_changes`/`update_artifact` render nothing in the transcript.

**(b) The steps strip renders tool activity itself, from agent events — NOT from the transcript.**
This follows an existing precedent: **`components/chat/WorkflowSteps.tsx`** already renders
intermediate steps by reading `useAgent({agentId}).subscribe(...)` events into its own panel. The
steps strip does the same: it subscribes to the agent's tool-call events and renders compact chips
in a strip **above the canvas**, decoupled from the chat transcript. It renders **generically** —
any tool call becomes a compact chip (skill tools → "🎨 skill: `<name>`"), and `update_artifact`
gets special treatment showing its inputs (`title`, `type`, `skill`, short `html` hint). It does
**not** hard-code or depend on a single `load_skill` name; whatever tool names the SkillsProvider
emits at runtime render as generic step chips (the plan verifies the real names via a live run /
the installed SDK — rule #1). Because the strip is event-driven (not `status`-driven), the HITL
non-terminal status never produces a stuck spinner.

This division removes the stuck/duplicated cards and gives the canvas its steps strip without trying
to hoist inline transcript renderers into a separate panel. The **detail page** has no agent, so it
uses neither mechanism.

## Screen 1 — Studio (create/edit): `ArtifactStudio.tsx` relayout

Reuse (unchanged behavior, only re-placed): `LivePreview`, the `respond(approved)` HITL resume, the
`pending` state, `useAgent().subscribe` (state snapshot/delta + `onEvent` approval capture),
`userEditedTitle` guard, the rAF-throttled `setHtml`, `regenerate()`, and `save()`.

New structure (top to bottom):

1. **Canvas header** — a single bar:
   - **Title** — inline-editable input (keeps `userEditedTitle` semantics: once edited, agent turns
     don't overwrite it).
   - **Type** — read-only chip, "definido pelo agente".
   - **Skill** — the existing `<select>` (Auto / slides / report / dashboard / walkthrough) +
     **Regenerate** button.
   - **Save as draft** — primary button (existing `save()`; disabled until `canSave`).
2. **Steps strip** — the self-rendered strip from Foundation (b): reads tool-call activity via
   `useAgent().subscribe` (WorkflowSteps.tsx pattern), collapsible; collapsed shows a one-line summary
   ("▸ 2 passos ✓"), expanded lists the skill chip(s) + `update_artifact` inputs. Default
   **collapsed**. Not populated by `renderToolCalls` (those only hide transcript cards).
3. **Main grid** — **Preview hero** (the big `LivePreview` iframe, primary column) + **thin chat
   rail** (the `<CopilotChat agentId="artifacts-studio" />` conversation + composer) as the secondary
   column. The chat rail shows only conversation (internal tool cards hidden via `renderToolCalls`).
   On narrow screens (<~760px) they stack (preview first, chat below).
4. **Review bar** — rendered over/above the preview **only when `pending` is set**: green bar
   "Revisar esta versão → Aprovar / Rejeitar", wired to `respond(true)` / `respond(false)`. While a
   run streams, the preview updates live; the bar appears when the approval interrupt fires. Save
   errors render inline near the Save action (existing `saveError`).

Interaction unchanged end-to-end: generate → stream into preview → approval interrupt → review bar →
approve (resume, artifact "lands") or reject (back to loop) → Save as draft → redirect to detail.

## Screen 2 — Detail: `ArtifactDetail.tsx` re-skin (same canvas language)

`ArtifactDetail.tsx` already has: a **status pill** (draft/pending_approval/published/rejected/
archived), **lifecycle action buttons** conditioned on status (`request-approval` when draft;
`approve`/`reject` when pending; `archive` when published/draft), an inline error banner, and the
`SandboxViewer` preview. Backend `require_role` remains the real enforcement point.

The DTO already carries everything the canvas header needs — **verified**: `_dto` in
`app/api/artifacts.py` returns `type`, `status`, `skill`, `version`, `contentHash`, and
`ArtifactDetail`'s `Artifact` type already consumes all of them. So the re-skin is **presentation
only — zero backend/DTO change** (consistent with the goal).

Re-skin to the canvas shell (no new logic):

- **Canvas header** — Title · Type chip · Skill chip (if present) · **status pill** · the existing
  lifecycle action buttons (role-gated server-side) + Open. Same `act(action)` calls.
- **Preview hero** — the `SandboxViewer` iframe as the large center element.
- **Metadata** — light strip/side (created, version, skill, content hash) from the existing DTO.
- **No steps strip, no chat** — a published artifact has no agent activity.

## Data flow & error handling

- Backend untouched: approval via `agent.runAgent({ resume: [...] })`; save via
  `POST /api/artifacts/create`; lifecycle via `POST /api/artifacts/{id}/{action}`.
- Generation failure clears `pending` (existing belt-and-suspenders in `regenerate`/`respond`).
- Reject → resume with `accepted:false` → back to the loop (unchanged).
- Save/lifecycle errors → inline banners (existing `saveError` / detail error banner).

## Testing

Add stable `data-testid`s to the restructured JSX so the E2E specs and the components don't drift.
Enumerated up front:

- **Studio:** `canvas-title` (title input), `skill-select`, `regenerate`, `save-draft`,
  `review-bar`, `review-approve`, `review-reject`, `steps-strip`.
- **Detail:** `status-pill`, `lifecycle-request-approval`, `lifecycle-approve`, `lifecycle-reject`,
  `lifecycle-archive`, `detail-open`.

Tests:

- **E2E `e2e/artifacts-studio.spec.ts`** — retarget to the ids above: approve via `review-approve`,
  pin skill via `skill-select` + `regenerate`, save via `save-draft`. Keep both existing cases (auto
  skill; slides override) green.
- **E2E `e2e/artifacts.spec.ts`** — the lifecycle case (seeded draft → detail) retargeted to the
  detail ids above.
- **Tool rendering** — assert the chat transcript shows **no** perpetual "Running" text after an
  approval (the internal tools are hidden) and that the `steps-strip` shows the skill + inputs. An
  E2E assertion is sufficient; a component test is optional.
- **Static** — `npm run typecheck` + `npm run build` (frontend job gates).

## Risks & mitigations

- **Bigger relayout than options A/B, and the detail page is in scope.** Mitigated by reusing every
  behavioral unit (LivePreview, respond/pending, save, act). New logic is limited to the
  subscribe-driven steps strip + the `renderToolCalls` hide entries; the rest is JSX restructure.
- **`renderToolCalls` API drift.** Verify `defineToolCallRenderer` / `useRenderTool` /
  `ToolCallStatus` against the installed `@copilotkit/react-core` before wiring (rule #1). Fall back
  to hiding via a wildcard `() => <></>` for all internal tools if the per-tool path differs.
- **Responsive breakage** in the two-column canvas. Explicit stack breakpoint + `overflow-x:auto` on
  wide preview content; verify in the build.

## Out of scope (future)

- Real artifact versioning (v2 on republish).
- Applying the canvas language to the list page.
- MCP Apps / A2A embedded artifact surfaces.
