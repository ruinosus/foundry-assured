# Artifacts Studio Canvas Redesign — Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign the Artifacts Studio (create/edit) and the artifact detail page into a "canvas" layout where the artifact is the hero, killing the duplicated/stuck "Running" tool cards by taking control of tool-call rendering.

**Architecture:** Frontend-only (no backend change). Two mechanisms: (1) `renderToolCalls` on `CopilotKitProvider` **hides** the internal HITL tools inside the `<CopilotChat>` transcript; (2) a new `StudioSteps` component renders tool activity itself from `agent.subscribe` events (the `WorkflowSteps.tsx` precedent). The Studio and the detail page share one canvas visual language; all existing behavior (LivePreview, HITL approval resume, save, lifecycle actions) is reused unchanged.

**Tech Stack:** Next.js 15 App Router, CopilotKit v2 (`@copilotkit/react-core/v2`), `@ag-ui/core` event types, Playwright E2E.

**Spec:** `docs/superpowers/specs/2026-07-07-artifacts-studio-canvas-redesign-design.md`

---

## Verified SDK facts (do not re-derive; confirmed against installed packages)

- `<CopilotKitProvider renderToolCalls={ReactToolCallRenderer[]}>` — prop lives on the provider
  (`CopilotKitCoreReactConfig.renderToolCalls`), **not** on `<CopilotChat>`.
- `ReactToolCallRenderer = { name: string; args?: schema; agentId?: string; render: React.ComponentType<{name,toolCallId,args,status,result}> }`.
  To hide a tool in the transcript: `render: () => <></>`.
- `ToolCallStatus` members: `InProgress | Executing | Complete` (not needed for the hide path).
- AG-UI events on `agent.subscribe({ onEvent })` (`event.type` is a string):
  - `"TOOL_CALL_START"` → `{ toolCallId, toolCallName }`
  - `"TOOL_CALL_ARGS"` → `{ toolCallId, delta }`  (args stream as JSON string fragments)
  - `"TOOL_CALL_END"` → `{ toolCallId }`
  - `"CUSTOM"` (name `function_approval_request` / `request_info`) → already handled in `ArtifactStudio` `onEvent` to set `pending`. **Hiding a tool's transcript render does NOT suppress this event.**
- `WorkflowSteps.tsx` precedent: a component with its own `useAgent({agentId})` + `agent.subscribe({onRunInitialized, onEvent, onRunFinalized})`. Multiple subscriptions to the same agent are supported (HelpdeskApp + WorkflowSteps both subscribe to `helpdesk`).

## Setup (once, before Chunk 1)

The worktree has no `node_modules` yet.

- [ ] From `apps/frontend/` in the worktree: `npm install` (installs the same pinned deps as the main repo).
- [ ] Baseline: `npm run typecheck` → expect PASS. `npm run build` → expect PASS.

**Running E2E** (chunk-end gate) needs both dev servers up in **auth-off + in-memory** mode:
```bash
# terminal 1 — backend (from apps/backend/)
ENTRA_TENANT_ID= ENTRA_API_CLIENT_ID= ENTRA_API_CLIENT_SECRET= ENTRA_SPA_CLIENT_ID= ARTIFACT_STORE_BACKEND=memory \
  uv run uvicorn app.main:app --port 8000 --reload
# terminal 2 — frontend (from apps/frontend/)
NEXT_PUBLIC_ENTRA_TENANT_ID= NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID= NEXT_PUBLIC_ENTRA_API_CLIENT_ID= npm run dev
# terminal 3 — E2E (from e2e/)
npx playwright test artifacts-studio.spec.ts artifacts.spec.ts
```
**E2E is a HARD gate, not optional.** The two new behaviors — "no stuck Running after approval" and
"steps-strip shows the skill/inputs" — are only observable at runtime; `typecheck`/`build` prove
nothing about them. If the implementer subagent cannot start the servers, it must **hand E2E to the
controller to run** (do not mark the chunk done on typecheck/build alone). The redesign is not
"working, testable software" until `artifacts-studio.spec.ts` (incl. the new assertions) is green.

## File structure

| File | Responsibility | Action |
| --- | --- | --- |
| `apps/frontend/components/artifacts/studioToolRenderers.tsx` | The `renderToolCalls` hide-list (internal HITL/skill tools → render nothing in transcript). | **Create** |
| `apps/frontend/components/artifacts/StudioSteps.tsx` | Tool-activity strip: subscribes to `agent` tool-call events, renders compact chips (skill generic + `update_artifact` inputs). | **Create** |
| `apps/frontend/components/artifacts/ArtifactStudio.tsx` | Canvas relayout: header (title/type/skill/save) + steps strip + preview-hero/chat-rail grid + review bar; pass `renderToolCalls` to the provider. | **Modify** |
| `apps/frontend/components/artifacts/ArtifactDetail.tsx` | Re-skin to canvas header (title/type/skill/status + lifecycle actions) + hero preview + metadata. | **Modify** |
| `e2e/artifacts-studio.spec.ts` | Retarget selectors to the new `data-testid`s; assert no stuck "Running". | **Modify** |
| `e2e/artifacts.spec.ts` | Retarget the detail lifecycle case to the new header `data-testid`s. | **Modify** |

**`data-testid` contract (add to JSX exactly as named):**
Studio — `canvas-title`, `skill-select`, `regenerate`, `save-draft`, `review-bar`, `review-approve`, `review-reject`, `steps-strip`.
Detail — `status-pill`, `lifecycle-request-approval`, `lifecycle-approve`, `lifecycle-reject`, `lifecycle-archive`, `detail-open`.

---

## Chunk 1: Foundation — hide internal tool cards + steps strip

### Task 1: `renderToolCalls` hide-list wired to the provider

**Files:**
- Create: `apps/frontend/components/artifacts/studioToolRenderers.tsx`
- Modify: `apps/frontend/components/artifacts/ArtifactStudio.tsx` (the `Studio` wrapper, ~line 399-408, where `<CopilotKitProvider runtimeUrl="/api/copilotkit">` wraps `<StudioCanvas/>`)

- [ ] **Step 1: Create the hide-list module**

```tsx
// studioToolRenderers.tsx
// The Studio's chat rail must stay a pure conversation: the internal HITL/skill tools
// (confirm_changes = the framework's approval pseudo-tool; update_artifact = approval-gated,
// so it never gets a terminal event and the default card sticks on "Running"; the SkillsProvider
// tools) are rendered elsewhere (StudioSteps) or not at all. Rendering nothing here removes the
// stuck/duplicated cards. Hiding the transcript render does NOT suppress the approval CUSTOM
// event — that is captured in StudioCanvas.onEvent and drives the review bar.
const HIDDEN_IN_TRANSCRIPT = [
  "confirm_changes",
  "update_artifact",
  "load_skill",
  "read_skill_resource",
  "run_skill_script",
];

// Shape matches ReactToolCallRenderer ({ name, render }). render returns an empty fragment.
export const studioToolRenderers = HIDDEN_IN_TRANSCRIPT.map((name) => ({
  name,
  render: () => <></>,
}));
```

- [ ] **Step 2: Pass it to the provider**

In `ArtifactStudio.tsx`, import `studioToolRenderers` and add the prop:
```tsx
import { studioToolRenderers } from "./studioToolRenderers";
// ...
<CopilotKitProvider
  runtimeUrl="/api/copilotkit"
  headers={authorization ? { Authorization: authorization } : undefined}
  renderToolCalls={studioToolRenderers}
>
```

- [ ] **Step 3: Typecheck**

Run (from `apps/frontend/`): `npm run typecheck`
Expected: PASS. If the `renderToolCalls` prop rejects the array shape, fix the element type in one
of two ways: (a) if `ReactToolCallRenderer` is exported, `import type { ReactToolCallRenderer } from
"@copilotkit/react-core/v2"` and annotate `export const studioToolRenderers: ReactToolCallRenderer<any>[]
= ...`; (b) if it is not exported, annotate the element inline —
`.map((name): { name: string; render: () => JSX.Element } => ({ name, render: () => <></> }))`.
Do NOT invent a different prop name — `renderToolCalls` is verified.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/components/artifacts/studioToolRenderers.tsx apps/frontend/components/artifacts/ArtifactStudio.tsx
git commit -m "feat(artifacts): hide internal HITL/skill tool cards in the Studio chat transcript"
```

### Task 2: `StudioSteps` — self-rendered tool-activity strip

**Files:**
- Create: `apps/frontend/components/artifacts/StudioSteps.tsx`
- Reference: `apps/frontend/components/chat/WorkflowSteps.tsx` (subscribe pattern)

- [ ] **Step 0 (SPIKE — de-risk before building): confirm which events fire for this agent**

`update_artifact` is `approval_mode="always_require"`, so its inputs arrive on the **CUSTOM
`function_approval_request`** event (this is how the existing `ArtifactStudio.onEvent` gets
`title`/`type`/`skill`/`html`) — the client-visible `TOOL_CALL_START`/`ARGS` may never fire for it.
So the strip's **primary** data source is that CUSTOM event (guaranteed), and `TOOL_CALL_START` is
**bonus** enrichment (skill tools like `load_skill`, which run un-gated).

Spike: temporarily add `console.log("EVT", event?.type, event?.name)` at the top of the existing
`onEvent` in `ArtifactStudio.tsx`, run the Studio (Setup servers), generate one artifact, and record
in this task which event types appear (expect at least `CUSTOM function_approval_request`; note
whether any `TOOL_CALL_START` appears and for which tool names). Remove the log after. Build
`StudioSteps` against what actually fires; the component below already defaults to the guaranteed path.

- [ ] **Step 1: Create the component** (primary = CUSTOM approval payload; TOOL_CALL_START = bonus)

```tsx
"use client";

// Tool-activity strip for the Studio canvas. Reads agent events directly (WorkflowSteps.tsx
// pattern), decoupled from the chat transcript and immune to the HITL non-terminal-status bug.
// PRIMARY source: the CUSTOM function_approval_request event carries update_artifact's inputs
// (title/type/skill) and always fires (it also drives the review bar) — same payload
// ArtifactStudio.onEvent already consumes. BONUS: TOOL_CALL_START names surface un-gated skill
// tools (load_skill, …). confirm_changes is never shown. Collapsible; collapsed by default.
import { useAgent } from "@copilotkit/react-core/v2";
import { useEffect, useState } from "react";

type Gen = { title?: string; type?: string; skill?: string };

export function StudioSteps() {
  const { agent } = useAgent({ agentId: "artifacts-studio" });
  const [gen, setGen] = useState<Gen | null>(null); // from the guaranteed CUSTOM approval event
  const [tools, setTools] = useState<string[]>([]); // bonus: un-gated tool names, if they fire
  const [open, setOpen] = useState(false);

  useEffect(() => {
    if (!agent) return;
    const sub = agent.subscribe({
      onRunInitialized: () => { setGen(null); setTools([]); },
      // eslint-disable-next-line @typescript-eslint/no-explicit-any
      onEvent: ({ event }: any) => {
        const t = event?.type;
        if (t === "CUSTOM" && (event?.name === "function_approval_request" || event?.name === "request_info")) {
          const fc = event.value?.function_call ?? {};
          let args: any = fc.arguments ?? {};
          if (typeof args === "string") { try { args = JSON.parse(args); } catch { args = {}; } }
          setGen({ title: args.title, type: args.type, skill: args.skill });
        } else if (t === "TOOL_CALL_START") {
          const name: string = event.toolCallName;
          if (name && name !== "confirm_changes" && name !== "update_artifact") {
            setTools((p) => (p.includes(name) ? p : [...p, name]));
          }
        }
      },
    });
    return () => sub.unsubscribe();
  }, [agent]);

  const chips: React.ReactNode[] = [];
  if (gen?.skill) chips.push(<span key="skill" className="step-chip">🎨 <b>skill: {gen.skill}</b></span>);
  for (const name of tools) chips.push(<span key={`t-${name}`} className="step-chip">🎨 <b>{name}</b></span>);
  if (gen) {
    const detail = [gen.title, gen.type].filter(Boolean).join(" · ");
    chips.push(
      <span key="gen" className="step-chip"><b>generated the artifact</b>
        {detail ? <span className="muted"> · {detail}</span> : null}</span>,
    );
  }
  if (chips.length === 0) return null;

  return (
    <div data-testid="steps-strip" className="steps-strip">
      <button className="steps-summary" onClick={() => setOpen((v) => !v)} aria-expanded={open}>
        <span aria-hidden>{open ? "▾" : "▸"}</span> {chips.length} step{chips.length > 1 ? "s" : ""} ✓
      </button>
      {open && <div className="steps-list">{chips}</div>}
    </div>
  );
}
```

Note: `event.value?.function_call?.arguments` mirrors `ArtifactStudio.onEvent` exactly (verified in
the current file, lines ~149–171) — do not change that access path.

- [ ] **Step 2: Add the strip's styles**

Add to the global stylesheet (find it: `grep -rl "acct-btn" apps/frontend/app` → the `globals.css`
that defines `.acct-btn`/`.pill`/`.muted`/`--border`). Append:
```css
.steps-strip { border: 1px solid var(--border); border-radius: 10px; background: var(--surface, #fff); }
.steps-summary { all: unset; cursor: pointer; display: flex; gap: 8px; align-items: center;
  padding: 8px 13px; font-size: 12.5px; font-weight: 600; width: 100%; box-sizing: border-box; }
.steps-summary:focus-visible { outline: 2px solid var(--accent, #2563eb); outline-offset: 2px; }
.steps-list { display: flex; gap: 12px; flex-wrap: wrap; padding: 0 13px 10px; }
.step-chip { font-size: 12px; }
```
Match the existing token names in that file (e.g. if it uses `--card` instead of `--surface`, use that).

- [ ] **Step 3: Typecheck**

Run: `npm run typecheck` → Expected: PASS.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/components/artifacts/StudioSteps.tsx apps/frontend/app/globals.css
git commit -m "feat(artifacts): StudioSteps — tool-activity strip from agent events"
```

### Chunk 1 review + integration gate

- [ ] Wire `<StudioSteps/>` is done in Chunk 2 (relayout). For now, confirm `npm run build` PASSES.
- [ ] Dispatch plan-document-reviewer is not needed here; proceed to Chunk 2.

---

## Chunk 2: Studio canvas relayout

### Task 3: Canvas header (title / type / skill / save)

**Files:**
- Modify: `apps/frontend/components/artifacts/ArtifactStudio.tsx` — replace the right-panel field
  block (current ~line 300-360: Title/Type labels, Skill select+Regenerate) and the Save button
  (~line 388-392) with a single top **canvas header**. Keep all state/handlers
  (`title`, `type`, `skill`, `usedSkill`, `userEditedTitle`, `regenerate`, `save`, `canSave`, `titleOk`).

- [ ] **Step 1: Build the header** (inside `StudioCanvas`'s returned JSX, as the first child)

Keep UI strings **English** to match the surrounding app ("Approve", "Save as draft", "Regenerate").
Preserve the `usedSkill` "Generated with:" indicator — the existing E2E asserts on it (see Task 5).

```tsx
<div className="canvas-header">
  <input
    data-testid="canvas-title"
    className="canvas-title-input"
    value={title}
    maxLength={MAX_TITLE}
    placeholder="Artifact title"
    onChange={(e) => { userEditedTitle.current = true; setTitle(e.target.value); }}
  />
  <span className="chip-type">{typeLabel}</span>
  <select
    data-testid="skill-select"
    className="acct-btn"
    style={{ width: "auto" }}
    value={skill}
    onChange={(e) => setSkill(e.target.value)}
  >
    {SKILLS.map((s) => (
      <option key={s} value={s}>{s === "auto" ? "Auto" : s[0].toUpperCase() + s.slice(1)}</option>
    ))}
  </select>
  <button
    data-testid="regenerate"
    className="acct-btn"
    style={{ width: "auto" }}
    disabled={!agent || approving || Boolean(pending) || regenerating}
    onClick={regenerate}
  >
    {regenerating ? "Regenerating…" : "Regenerate"}
  </button>
  <button data-testid="save-draft" className="btn btn-solid" disabled={!canSave} onClick={save}>
    {saving ? "Saving…" : "Save as draft"}
  </button>
</div>
{usedSkill && (
  <span data-testid="used-skill" className="muted" style={{ fontSize: 12, margin: "0 2px" }}>
    Generated with: {usedSkill}
  </span>
)}
{!titleOk && title.length > 0 && (
  <p className="muted" style={{ margin: "4px 2px 0", fontSize: 12 }}>
    Title must be between 1 and {MAX_TITLE} characters.
  </p>
)}
```

- [ ] **Step 2: Header styles** (append to the same globals.css as Task 2)

```css
.canvas-header { display: flex; align-items: center; gap: 10px; flex-wrap: wrap;
  padding: 10px 12px; border: 1px solid var(--border); border-radius: 12px; background: var(--surface, #fff); }
.canvas-title-input { flex: 1; min-width: 200px; font-size: 15px; font-weight: 600;
  border: 1px solid transparent; background: transparent; color: inherit; padding: 6px 8px; border-radius: 8px; }
.canvas-title-input:hover { border-color: var(--border); }
.canvas-title-input:focus-visible { outline: 2px solid var(--accent, #2563eb); outline-offset: 1px; }
.chip-type { font-size: 12px; color: var(--muted, #64748b); border: 1px solid var(--border);
  border-radius: 999px; padding: 4px 10px; white-space: nowrap; }
```

- [ ] **Step 3: Typecheck** → `npm run typecheck` → PASS.
- [ ] **Step 4: Commit**

```bash
git add apps/frontend/components/artifacts/ArtifactStudio.tsx apps/frontend/app/globals.css
git commit -m "feat(artifacts): Studio canvas header (title/type/skill/save)"
```

### Task 4: Main grid (preview hero + chat rail) + review bar + StudioSteps

**Files:**
- Modify: `apps/frontend/components/artifacts/ArtifactStudio.tsx` — replace the outer two-column
  layout (current ~line 279-395, `<div style={{ display:"flex", gap:16 }}>` with chat-left /
  panel-right) with: header (Task 3) → `<StudioSteps/>` → main grid (preview hero + chat rail) with
  the review bar over the preview. Remove the old right-panel approval card (~line 362-380) and the
  old `usedSkill` "Generated with" line if redundant (keep it small under the header if desired).

- [ ] **Step 1: Import StudioSteps**
```tsx
import { StudioSteps } from "./StudioSteps";
```

- [ ] **Step 2: New layout — the COMPLETE `StudioCanvas` return** (this folds in Task 3's header;
  the two commits together replace the old two-column return, so between them the app still builds).
  Paste the Task 3 header markup verbatim where indicated — do not leave it as a comment.

```tsx
return (
  <div className="studio-canvas">
    {/* === Task 3 canvas-header block goes here, verbatim: the <div className="canvas-header">…</div>,
           the used-skill <span>, and the title-length helper <p>. === */}
    <StudioSteps />
    <div className="studio-grid">
      <div className="preview-hero">
        {pending && (
          <div data-testid="review-bar" className="review-bar">
            <span className="review-text">Review this version before applying</span>
            <button data-testid="review-approve" className="btn btn-solid" onClick={() => respond(true)}>
              Approve
            </button>
            <button data-testid="review-reject" className="acct-btn" onClick={() => respond(false)}>
              Reject
            </button>
          </div>
        )}
        <LivePreview html={html || "<!doctype html><html><body></body></html>"} />
        {saveError && <p className="muted" style={{ margin: "8px 0 0" }}>⚠️ {saveError}</p>}
      </div>
      <div className="chat-rail">
        <CopilotChat agentId="artifacts-studio" />
      </div>
    </div>
  </div>
);
```

> Practical ordering: it is fine to do Task 3 and Task 4 as one edit of the return (header + grid
> together) and commit once, if that reads cleaner than two commits — the goal is a single coherent
> new return with no leftover old two-column markup.

- [ ] **Step 3: Layout styles** (append to globals.css)

```css
.studio-canvas { display: flex; flex-direction: column; gap: 12px; }
.studio-grid { display: grid; grid-template-columns: minmax(0, 1fr) 320px; gap: 14px; min-height: 70vh; }
.preview-hero { display: flex; flex-direction: column; gap: 10px; min-width: 0; }
.chat-rail { border: 1px solid var(--border); border-radius: 12px; overflow: hidden; display: flex; min-height: 70vh; }
.chat-rail > * { flex: 1; min-height: 0; }
.review-bar { display: flex; align-items: center; gap: 12px; padding: 10px 14px; border-radius: 10px;
  background: var(--good-weak, #dcfce7); border: 1px solid var(--good, #16a34a); }
.review-text { flex: 1; font-size: 13px; font-weight: 600; color: var(--good, #16a34a); }
@media (max-width: 760px) { .studio-grid { grid-template-columns: 1fr; } .chat-rail { min-height: 380px; } }
```
If globals.css has no `--good`/`--good-weak`, add them near the other tokens (light + dark blocks):
`--good:#16a34a; --good-weak:#dcfce7;` (dark: `--good:#22c55e; --good-weak:#13351f;`).

- [ ] **Step 4: Delete dead code** — remove the old `card` style usage / right-panel approval block
  and the old two-column wrapper now replaced. Keep `card`/`btn` helpers only if still referenced
  (`grep -n "card\b\|btn(" ArtifactStudio.tsx`).

- [ ] **Step 5: Typecheck + build** → `npm run typecheck && npm run build` → PASS.
- [ ] **Step 6: Commit**

```bash
git add apps/frontend/components/artifacts/ArtifactStudio.tsx apps/frontend/app/globals.css
git commit -m "feat(artifacts): Studio canvas grid — preview hero + chat rail + review bar"
```

### Task 5: E2E — retarget artifacts-studio.spec.ts

**Files:**
- Modify: `e2e/artifacts-studio.spec.ts`

- [ ] **Step 1: Update selectors** to the new `data-testid`s: approve via
  `getByTestId("review-approve")`, pin skill via `getByTestId("skill-select")` + `getByTestId("regenerate")`,
  save via `getByTestId("save-draft")`.
  - **Preserve the skill-override check:** the current test asserts `Generated with: slides`
    (spec's only verification of that case). Replace the old text locator with the testid'd element:
    `await expect(page.getByTestId("used-skill")).toContainText(/slides/i)`.
  - **New assertions:** after a generation, `await expect(page.getByTestId("steps-strip")).toBeVisible()`;
    after approving, the transcript shows no stuck status —
    `await expect(page.getByText("Running")).toHaveCount(0)`.
- [ ] **Step 2: Run E2E** (servers up per Setup): `npx playwright test artifacts-studio.spec.ts`
  Expected: both cases (auto skill; slides override) PASS; the no-"Running" assertion PASS.
- [ ] **Step 3: Commit**

```bash
git add e2e/artifacts-studio.spec.ts
git commit -m "test(artifacts): retarget studio E2E to canvas testids + assert no stuck Running"
```

### Chunk 2 review

- [ ] Dispatch plan-document-reviewer / code-quality review per subagent-driven-development before Chunk 3.

---

## Chunk 3: Detail canvas re-skin + final verification

### Task 6: `ArtifactDetail` canvas header + hero

**Files:**
- Modify: `apps/frontend/components/artifacts/ArtifactDetail.tsx` (125 lines; reuse `act`, status
  conditions, `SandboxViewer`, error banner — presentation only, zero logic change).

- [ ] **Step 1: Re-skin the return** to the canvas header + hero shape:

```tsx
return (
  <div className="studio-canvas">
    <div className="canvas-header">
      <span className="canvas-title-input" style={{ pointerEvents: "none" }}>{a.title}</span>
      <span className="chip-type">{a.type}</span>
      {a.skill && <span className="chip-type">🎨 {a.skill}</span>}
      <span data-testid="status-pill" className={`pill ${STATUS[a.status] ?? "neutral"}`}>{a.status}</span>
      <span className="muted">v{a.version}</span>
      <span style={{ flex: 1 }} />
      {a.status === "draft" && (
        <button data-testid="lifecycle-request-approval" className="btn btn-solid" disabled={busy}
          onClick={() => act("request-approval")}>Request approval</button>
      )}
      {a.status === "pending_approval" && (
        <>
          <button data-testid="lifecycle-approve" className="btn btn-solid" disabled={busy}
            onClick={() => act("approve")}>Approve</button>
          <button data-testid="lifecycle-reject" className="acct-btn" disabled={busy}
            onClick={() => act("reject")}>Reject</button>
        </>
      )}
      {(a.status === "published" || a.status === "draft") && (
        <button data-testid="lifecycle-archive" className="acct-btn" disabled={busy}
          onClick={() => act("archive")}>Archive</button>
      )}
      <a data-testid="detail-open" className="acct-btn" style={{ width: "auto" }}
        href={`/api/artifacts/${a.id}/content`} target="_blank" rel="noreferrer">Open</a>
    </div>
    {error && <p className="muted" style={{ margin: 0 }}>⚠️ {error}</p>}
    <div className="preview-hero">
      <SandboxViewer artifactId={a.id} />
    </div>
    {a.description && <p className="muted" style={{ margin: 0, fontSize: 13 }}>{a.description}</p>}
  </div>
);
```
Keep the existing `STATUS` map, `a` type, `act`, `busy`, `error`, load `useEffect`. Confirm the
`/api/artifacts/{id}/content` proxy route exists (`grep -rn "content" apps/frontend/app/api/artifacts`);
if the "Open" href differs, use the real one or drop the Open button (it's additive, not required).

- [ ] **Step 2: Typecheck + build** → PASS.
- [ ] **Step 3: Commit**

```bash
git add apps/frontend/components/artifacts/ArtifactDetail.tsx
git commit -m "feat(artifacts): detail page — canvas header + hero preview"
```

### Task 7: E2E detail + full verification

**Files:**
- Modify: `e2e/artifacts.spec.ts` (the lifecycle case that seeds a draft and visits the detail page).

- [ ] **Step 1: Retarget** the detail lifecycle assertions/clicks to `getByTestId("status-pill")`,
  `getByTestId("lifecycle-request-approval")`, `lifecycle-approve`, etc.
- [ ] **Step 2: Run full E2E** (servers up): `npx playwright test artifacts.spec.ts artifacts-studio.spec.ts`
  Expected: all cases PASS.
- [ ] **Step 3: Static gates** (from `apps/frontend/`): `npm run typecheck && npm run build` → PASS.
- [ ] **Step 4: Commit**

```bash
git add e2e/artifacts.spec.ts
git commit -m "test(artifacts): retarget detail lifecycle E2E to canvas testids"
```

### Final review

- [ ] Dispatch a final code-reviewer over the whole branch diff vs `develop`.
- [ ] Use superpowers:finishing-a-development-branch (push + PR to `develop`, watch CI).

---

## Notes for the implementer

- **No backend changes.** If any task seems to need one, stop — the design says zero backend/DTO change.
- **Reuse, don't rewrite** the behavioral units in `ArtifactStudio.tsx`: `subscribe`/`onEvent` (approval → `pending`), `respond`, `regenerate`, `save`, `scheduleSetHtml`, `userEditedTitle`. Only their placement changes.
- **Rule #1:** every SDK surface here is verified above. If something diverges at build time, verify against the installed package before changing the call — do not guess.
- **Token names:** match whatever the existing `globals.css` uses (`--border`, `--muted`, `--accent`, card/surface). Grep before adding new tokens.
