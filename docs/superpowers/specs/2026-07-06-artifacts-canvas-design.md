---
title: HTML Artifacts Studio — interactive canvas (chat + live preview) design
description: A CopilotKit + AG-UI generative-UI canvas for creating HTML artifacts conversationally, with a live sandboxed preview streamed via AG-UI shared/predictive state and native in-loop edit confirmation, handing off to the existing artifact lifecycle.
type: design
status: draft
updated: 2026-07-06
---

# HTML Artifacts Studio — interactive canvas design

## 1. Context & goal

The MVP artifact creation UI is a simple form (`ArtifactsView`) that POSTs one prompt to a
non-streaming `POST /artifacts/html/generate` endpoint and shows nothing until the LLM finishes.
Feedback: (a) the form lacks validations, and (b) it should be a **modern, interactive experience
where the HTML renders live as it is generated**, using **CopilotKit** — the frontend stack we
already run.

**Goal:** replace the simple creation form with an **Artifacts Studio** — a conversational canvas
(chat on the left, a live sandboxed HTML preview on the right) where the user describes and
iteratively refines an artifact, watches it build in real time, confirms each proposed edit
in-loop, and saves the result as a **draft** that enters the existing approve-to-publish lifecycle.

This is **not** a new generation mechanism bolted on — it uses the **native Microsoft Agent
Framework AG-UI shared-state / predictive-state** feature, which our stack already depends on.

## 2. Background & references (verified)

- Our backend already mounts domain agents through `agent_framework_ag_ui.add_agent_framework_fastapi_endpoint`
  (`app/domains.py::mount_domains`), and the frontend registers one CopilotKit `HttpAgent` per
  backend AG-UI endpoint (`app/api/copilotkit/[[...slug]]/route.ts`).
- **Verified against the installed package** (`agent-framework-ag-ui==1.0.0rc5`): `AgentFrameworkAgent.__init__`
  accepts `agent, name, description, state_schema, predict_state_config, require_confirmation,
  use_service_session, snapshot_store`. So the design below uses only real, pinned APIs (CLAUDE.md rule #1).
- **Native pattern** ([MS Learn — AG-UI State Management, Python](https://learn.microsoft.com/en-us/agent-framework/integrations/ag-ui/state-management)):
  an agent exposes a `state_schema` field and a `@tool` that writes the **complete** object; a
  `predict_state_config` maps the tool argument to the state field, so the framework streams
  `STATE_DELTA` (JSON-Patch) events as the LLM generates the tool arguments — optimistic, live UI.
  `require_confirmation=True` emits a `FUNCTION_APPROVAL_REQUEST` before applying the change.
- **Frontend pattern — grounded in this repo's ACTUAL CopilotKit v2 usage (NOT the v1 hooks the MS/CopilotKit blogs show).**
  This app imports from `@copilotkit/react-core/v2` and does **not** use `useCoAgent`/`useCopilotAction`
  (those aren't exported from `/v2`, and importing them from `/v2/headless` hits a separate-context bug
  the repo already documented in `components/chat/WorkflowSteps.tsx:9-14`). The real pattern:
  `<CopilotKitProvider runtimeUrl=... headers=...>` + `useAgent({ agentId })` from `/v2`, plus a **manual
  event tap** `agent.subscribe({ onEvent, onStateSnapshotEvent, onStateDeltaEvent })` to read the streamed
  `artifact.html` and to catch the approval event, resolved with `agent.runAgent({ resume: [...] })`. This
  is exactly how `components/chat/TicketApproval.tsx` handles the agent-framework interrupt today (it notes
  CopilotKit's `useInterrupt` "doesn't pick up the agent-framework workflow interrupt" because the adapter
  emits a `CUSTOM` event). Verified in the installed `agent_framework_ag_ui==1.0.0rc5`: `require_confirmation=True`
  emits a `CustomEvent(name="function_approval_request", ...)` + a synthetic `confirm_changes` tool sequence,
  resolved through the same interrupt/resume machinery — so the Studio extends `TicketApproval.tsx`'s tap,
  it does not get a free higher-level hook.
- **Reference implementation to mirror for wiring** ([`jspoelstra/ag-ui-foundry`](https://github.com/jspoelstra/ag-ui-foundry), MIT):
  Foundry v2 + agent-framework + FastAPI backend with `update_*` tools mapped via `predict_state_config`;
  Next.js + CopilotKit frontend using `useCoAgent()` to render a live-updating card. We edit an HTML
  document instead of a project card. MIT — safe to reuse as a reference.

## 3. Non-goals (out of scope)

- Replacing the one-shot `POST /artifacts/html/generate` endpoint — it stays (used by the existing
  Playwright E2E and as a possible headless path). Only the **inline creation form UI** is replaced.
- Changing the artifact **lifecycle/governance** (draft → pending_approval → published, Approver/Admin,
  immutability + SHA-256). The Studio produces a draft; publishing is unchanged.
- Server-side conversation persistence beyond what AG-UI threads provide. No artifact is persisted
  until the user clicks **Save as draft** (no orphan drafts).
- External assets / multi-file artifacts (self-contained HTML only, per the MVP decision).
- Diff/version-compare UI, collaborative multi-user editing.

## 4. Two distinct approvals (do not conflate)

| Approval | What it gates | Where | Who |
|---|---|---|---|
| **Canvas edit confirmation** (`require_confirmation=True`) | accept/reject each HTML edit the agent proposes, in-loop, before it becomes the current working artifact | Studio chat (native `FUNCTION_APPROVAL_REQUEST` → approval card) | any Author in the Studio |
| **Lifecycle publish approval** | promote a saved draft to `published` (immutable + hashed) | artifact detail page | **Approver/Admin** (`require_role`) |

The canvas confirmation improves *authoring* (preview-and-accept, non-destructive refine). The
governance gate on *publishing* is unchanged.

## 5. Architecture overview

```
┌──────────────────────────────────────────────┐        ┌────────────────────────────┐
│ /artifacts/new  (Next.js, AppShell)           │        │ FastAPI backend            │
│  ┌───────────── ArtifactStudio ────────────┐  │        │                            │
│  │ <CopilotChat agentId="artifacts-studio">│  │  AG-UI │  /artifacts-studio         │
│  │   describe / refine …                   │──┼───SSE──┼─▶ AgentFrameworkAgent(      │
│  │   [approval card: Apply this version?]  │◀─┼────────┼─   state_schema, predict_,  │
│  │                                         │  │ STATE_ │    require_confirmation)     │
│  │ agent.subscribe → artifact.html ───────▶│  │ DELTA/ │      └─ update_artifact tool │
│  │   → <SandboxViewer html> (LIVE)         │  │ SNAPSHOT│                            │
│  │ [ Save as draft ]───────────────────────┼──┼──POST──┼─▶ POST /artifacts/html      │
│  └─────────────────────────────────────────┘  │        │    → validate + create_draft│
└──────────────────────────────────────────────┘        └────────────────────────────┘
        via /api/copilotkit (runtime)  +  /api/artifacts proxy
```

## 6. Backend design

### 6.1 State model + tool (`app/agents/artifacts_studio.py`, new)

```python
from pydantic import BaseModel, Field
from agent_framework import tool

class ArtifactDraft(BaseModel):
    html: str = Field(..., description="The COMPLETE self-contained HTML document, starting with <!doctype html>.")

@tool
def update_artifact(artifact: ArtifactDraft) -> str:
    """Write the COMPLETE updated HTML document. Always include the full document — never a diff,
    never a partial. When refining, keep everything and apply the requested change."""
    return "Artifact updated."
```

- `title`/`type` are **not** in the agent state — they are metadata the user sets in the Studio UI at
  save time (keeps the agent focused on HTML, avoids the model inventing titles). The state is just
  `{ "artifact": { "html": ... } }`.

### 6.2 Studio agent (per-request, mirrors `app/agents/platform.py` / `per_request.py`)

- Build an agent-framework `Agent` with the Foundry model (`tenant_config().foundry_model`,
  `foundry_project_endpoint`) and the caller's per-request OBO credential — mirror how `platform.py`
  constructs a per-request agent (the studio needs the signed-in user's credential, like other domains).
- System instructions: it is an HTML artifact author; it MUST call `update_artifact` with the complete
  document starting with `<!doctype html>`, self-contained (inline CSS/JS, no external requests), safe
  to render in a sandboxed iframe; after updating, reply with a 1-sentence summary.
- Wrap:

```python
from agent_framework_ag_ui import AgentFrameworkAgent
studio = AgentFrameworkAgent(
    agent=agent,
    name="ArtifactsStudio",
    description="Conversationally generates and refines a self-contained HTML artifact.",
    state_schema={"artifact": {"type": "object", "description": "The current HTML artifact draft"}},
    predict_state_config={"artifact": {"tool": "update_artifact", "tool_argument": "artifact"}},
    require_confirmation=True,
)
```

### 6.3 Mounting `/artifacts-studio`

- Mount via `add_agent_framework_fastapi_endpoint(app, studio, "/artifacts-studio")` from
  `mount_domains` (or a sibling mount in `app/main.py`). It is a **bespoke** endpoint, NOT a
  `/d/[domain]` registry domain — the Studio is its own canvas page, so we don't add it to
  `apps/frontend/lib/domains.ts` (that would put an artifacts chat in the generic domain console).
- **Auth (resolved — not an open risk):** `add_agent_framework_fastapi_endpoint` accepts a
  `dependencies=` sequence (verified in the installed package), and `app/domains.py::_mount_helpdesk`/`_mount_platform`
  already pass `dependencies=_domain_deps(d.id)` to gate the live `/helpdesk`/`/platform` AG-UI endpoints.
  So the Studio mount is simply:
  `add_agent_framework_fastapi_endpoint(app, agent=studio, path="/artifacts-studio", dependencies=[*auth_dependencies(), Depends(require_role("Author","Admin"))])`
  — reusing the exact `require_role("Author","Admin")` pair already declared in `app/api/artifacts.py:17`. No new mechanism.

### 6.4 Create-from-HTML endpoint (`app/api/artifacts.py`)

```
POST /artifacts/html      (dependencies=[require_role("Author","Admin")])
  body: { title: str, description: str = "", type: str, html: str }
  -> svc.create_draft(tenant_id=artifact_tenant_id(), title, description, type, html, user=current_user())
  -> 201 DTO   (422 on ValueError: bad type / validation / length)
```

- Reuses the existing `create_draft` (validates via `validate_html`, tenant-scoped).
- **Add server-side length caps**: `title` ≤ 200, `description` ≤ 1000 (reject with 422). Put the caps
  in the service (`create_draft`) so both this endpoint and any future caller are covered.

## 7. Frontend design

### 7.1 `app/artifacts/new/page.tsx` (new)

Thin AppShell wrapper around `<ArtifactStudio />` (client component).

### 7.2 `components/artifacts/ArtifactStudio.tsx` (new) — **built on the repo's v2 pattern**

Mirror `components/chat/HelpdeskApp.tsx` (provider) + `WorkflowSteps.tsx` (`useAgent` + `agent.subscribe`)
+ `TicketApproval.tsx` (interrupt tap + `runAgent({resume})`). Do NOT use `useCoAgent`/`useCopilotAction`.

- **Provider:** `<CopilotKitProvider runtimeUrl="/api/copilotkit" headers={authorization ? { Authorization: authorization } : undefined}>`
  (token from `acquireTokenSilent`, exactly as `HelpdeskApp.tsx:28-30`).
- **Chat + agent handle:** `<CopilotChat agentId="artifacts-studio" />` for the conversation; get the agent
  handle with `const agent = useAgent({ agentId: "artifacts-studio" })` (from `@copilotkit/react-core/v2`).
- **Layout:** two columns — chat (left), live preview + metadata + Save (right).
- **Live preview (shared state):** subscribe once — `agent.subscribe({ onStateSnapshotEvent, onStateDeltaEvent })`
  — accumulate the `artifact.html` field (snapshot = full state; delta = JSON-Patch on `/artifact`) into a
  React state string, and feed it to the sandbox iframe (reuse the `SandboxViewer` iframe: `sandbox="allow-scripts"`,
  no `allow-same-origin`, `srcDoc`). Throttle `srcDoc` writes with `requestAnimationFrame` to avoid flicker on
  partial HTML. (If reading `agent.state` directly is simpler/reliable in v2, that is an acceptable equivalent —
  the plan verifies which the installed version exposes; the subscribe tap is the fallback that definitely works.)
- **Edit confirmation (interrupt tap):** in `agent.subscribe({ onEvent })`, detect the
  `function_approval_request` CUSTOM event (same tap `TicketApproval.tsx` uses for the platform write-tool
  approval), render an approval card ("Apply this version? [Approve] [Reject]"), and resolve with
  `agent.runAgent({ resume: [{ /* approvalId/interruptId + status + payload */ }] })`. The exact event field
  names + resume payload shape are verified live during implementation (TicketApproval.tsx itself flags this
  as "pending live verification").
- **Metadata + Save:** Title input + Type select (report/presentation/walkthrough). **Save as draft**
  button → `POST /api/artifacts/html { title, type, html }` (html = the accumulated confirmed artifact) →
  on success redirect to `/artifacts/[id]`.

### 7.3 `app/api/artifacts/route.ts` (extend)

Add a `POST`-with-html branch OR a distinct handler so the Studio can call the create-from-html endpoint.
(The existing `POST /api/artifacts` proxies to `/generate`; add create-from-html without breaking it —
e.g. route on a body discriminator, or add `app/api/artifacts/create/route.ts`. Plan decides; keep the
one-shot generate path intact.)

### 7.4 `app/api/copilotkit/[[...slug]]/route.ts` (extend)

Register an `HttpAgent` keyed `"artifacts-studio"` → `${BACKEND}/artifacts-studio` (mirror the manual
hosted-twin registrations). Interrupt-bearing (require_confirmation), so it gets the resume bridge like
the workflow/tool agents.

### 7.5 `components/artifacts/ArtifactsView.tsx` (modify)

Replace the inline "Generate HTML artifact" form with a **"＋ New artifact"** button linking to
`/artifacts/new`. The list, statuses, and links are unchanged.

### 7.6 Nav

`/artifacts/new` is a sub-route of the existing Artifacts nav item (breadcrumb prefix-match already
resolves it to "Artifacts"). No new sidebar entry.

## 8. Validations

**Client (Studio):**
- Title required, ≤ 200 chars; Type from the fixed select.
- Chat input non-empty, ≤ 4000 chars (guard against runaway prompts).
- **Save as draft** disabled unless: Title present AND Type selected AND `state.artifact.html` non-empty.
- Inline field-level messages (reuse the `muted`/error idiom).

**Server:**
- `create_draft` enforces type ∈ ALLOWED_TYPES + `validate_html` (size/shape) — already present.
- **New:** title ≤ 200, description ≤ 1000 → 422 (added to `create_draft`).

## 9. Security

- Live preview reuses the sandbox boundary (`sandbox="allow-scripts"`, no `allow-same-origin`, `srcDoc`).
  Partial/streaming HTML is still sandboxed (opaque origin) — safe to render before completion.
- `/artifacts-studio` and `POST /artifacts/html` are Author/Admin gated. The confirmed HTML is
  re-validated server-side on save (`validate_html`).
- No secrets in state; the agent uses the per-request OBO credential (auth on) or DefaultAzureCredential
  (auth off / local), same as other domains.

## 10. Testing

**Backend (runner-style `*_test.py`, `uv run python -m eval.<name>`):**
- `POST /artifacts/html` create-from-html: route wiring + role gate (extend `artifact_rbac_test`), and a
  service test for the new length caps.
- Studio agent/tool: unit-test `update_artifact` + the agent construction with the **LLM boundary mocked**
  (do not call Azure) — assert the state field maps to the tool argument (`predict_state_config` shape).
  Full AG-UI streaming is validated by E2E, not a unit test (no HTTP harness in this repo).

**E2E (Playwright, local auth-off):** extend `e2e/artifacts.spec.ts` or add `artifacts-studio.spec.ts`:
open `/artifacts/new`, send a prompt → preview populates (live), approve the edit card, send a refine →
preview changes, approve, set Title, **Save as draft** → lands on `/artifacts/[id]` as `draft`.

## 11. File structure (create / modify)

**Backend:**
- Create `app/agents/artifacts_studio.py` — `ArtifactDraft`, `update_artifact`, per-request studio agent factory.
- Modify `app/domains.py` (or `app/main.py`) — mount `/artifacts-studio`.
- Modify `app/api/artifacts.py` — `POST /artifacts/html` (create-from-html), Author/Admin gate.
- Modify `app/services/artifacts.py` — title/description length caps in `create_draft`.
- Modify `eval/artifact_rbac_test.py` + `eval/artifact_service_test.py` — new route gate + caps.
- Create `eval/artifact_studio_test.py` — tool/state-mapping unit test (LLM mocked).

**Frontend:**
- Create `app/artifacts/new/page.tsx`, `components/artifacts/ArtifactStudio.tsx`.
- Reuse/extract the sandbox iframe from `SandboxViewer.tsx` into a shared `LivePreview` (or accept an
  `html` string prop) so both the detail viewer and the Studio share one sandbox component.
- Modify `app/api/copilotkit/[[...slug]]/route.ts` — register `"artifacts-studio"` HttpAgent.
- Add create-from-html proxy (`app/api/artifacts/create/route.ts` or a branch in the existing route).
- Modify `components/artifacts/ArtifactsView.tsx` — form → "＋ New artifact" link.

**E2E:** add/extend the Playwright spec.

## 12. Risks & open questions

- **Partial-HTML rendering:** streaming `STATE_DELTA` yields incomplete HTML mid-generation; the sandbox
  renders it progressively. Mitigate flicker with rAF-throttled `srcDoc` writes; accept that mid-stream
  frames may look unfinished (that is the "building live" effect). If flicker is bad, only re-render on
  `STATE_SNAPSHOT` (post-confirmation) and show a lightweight "generating…" state during deltas.
- **Model discipline:** the tool contract requires the **complete** document every turn. If the model
  emits partial/diff HTML, refines could drop content. The system prompt must be emphatic (mirror the
  recipe example's "NEVER delete existing data"). Covered by E2E refine assertion.
- **AG-UI interrupt/state event shapes:** the exact field names of the `function_approval_request` /
  `confirm_changes` events and the `runAgent({resume})` payload must be verified live during implementation
  (as `TicketApproval.tsx` already notes for the platform write-approval). The mechanism is proven (workflow
  HITL + platform tool-approval both use it); only the artifact-specific field wiring is to confirm.
- **CopilotKit version:** we run `@copilotkit/react-core` **v1.62.1 consumed via the `/v2` entrypoint** and
  `agent-framework-ag-ui` 1.0.0rc5. The design uses `useAgent` + `agent.subscribe`/`runAgent` from `/v2`
  (verified in-repo usage) — NOT `useCoAgent`/`useCopilotAction` (not exported from `/v2`) and NOT
  OpenGenerativeUI's v2 `useComponent`.

## 13. Reference wiring (from `jspoelstra/ag-ui-foundry`, MIT)

- `backend/server.py` / `backend/state.py` — `update_*` tools + `predict_state_config` mapping, Foundry
  agent construction (both "local agent calling Foundry" and "direct Foundry agent" modes).
- `frontend/app/page.tsx` — `useCoAgent()` binding + `CopilotChat`. We swap the ProjectCard for our
  sandboxed `LivePreview`.
