# Artifacts Studio (canvas) Implementation Plan

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the simple artifact-creation form with an **Artifacts Studio** — a CopilotKit + AG-UI conversational canvas where the user describes and refines an HTML artifact, watches it stream live into a sandboxed preview, confirms each proposed edit in-loop, and saves it as a draft that enters the existing lifecycle.

**Architecture:** A backend agent-framework agent exposes the HTML as AG-UI **shared/predictive state** (`AgentFrameworkAgent(state_schema, predict_state_config, require_confirmation=True)`), mounted at `/artifacts-studio`. The frontend `/artifacts/new` canvas uses this repo's **CopilotKit v2** pattern (`<CopilotKitProvider>` + `useAgent({agentId})` + a manual `agent.subscribe`/`runAgent({resume})` tap, exactly like `TicketApproval.tsx`/`WorkflowSteps.tsx`) to render the streamed `artifact.html` in the sandboxed `SandboxViewer` and to drive the native edit-approval card. "Save as draft" POSTs the confirmed HTML to a new create-from-html endpoint that reuses `create_draft`.

**Tech Stack:** Python 3.12 · `agent-framework` (`FoundryChatClient.as_agent`, `@tool`) · `agent-framework-ag-ui==1.0.0rc5` (`AgentFrameworkAgent`, `add_agent_framework_fastapi_endpoint`) · FastAPI · `DefaultAzureCredential`/OBO · Next.js 16 / React 19 · `@copilotkit/react-core/v2` + `@copilotkit/runtime/v2` + `@ag-ui/client` · Playwright.

**Spec:** `docs/superpowers/specs/2026-07-06-artifacts-canvas-design.md` (read it — this plan implements it).

**Verified against installed packages:** `AgentFrameworkAgent.__init__(agent, name, description, state_schema, predict_state_config, require_confirmation, use_service_session, snapshot_store)` (rc5); `useAgent`/`agent.subscribe`/`agent.runAgent({resume})` are the repo's real v2 usage (`WorkflowSteps.tsx`, `TicketApproval.tsx`). Do NOT use `useCoAgent`/`useCopilotAction` (not exported from `/v2`).

---

## Ground rules (read once)

- **Work from** `/Users/jefferson.barnabe/projects/foundry-helpdesk/.worktrees/html-artifacts` (branch `feature/html-artifacts`).
- **No pytest.** Backend tests are `main() -> int` modules run with `uv run python -m eval.<name>` from `apps/backend/`. The `VIRTUAL_ENV … does not match` warning is harmless.
- **Frontend has no unit harness** — verify with `npx tsc --noEmit` + `npm run build` + Playwright E2E.
- **CLAUDE.md rule #1:** all SDK surfaces below are copied from real, working repo files (cited per task). If something drifts, mirror the real file — do not invent.
- **Commit per task** with the given message + trailer `Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>`. Do NOT amend earlier commits. There is a pre-existing unstaged `apps/frontend/package-lock.json` (+ dev-server-touched `tsconfig.json`/`next-env.d.ts`) — never stage those; stage only each task's files.
- Local dev servers may be running (backend `:8010`, frontend `:3010`, auth off, `ARTIFACT_STORE_BACKEND=memory`). Hot-reload picks up edits; do not restart them.

---

## File structure

**Backend (`apps/backend/`):**
- Create `app/agents/artifacts_studio.py` — `ArtifactDraft` (Pydantic), `update_artifact` `@tool`, `build_studio_agent()` factory, the `PerRequestAgent`-wrapped `AgentFrameworkAgent` studio instance, and `mount_artifacts_studio(app)`.
- Modify `app/main.py` — call `mount_artifacts_studio(app)` next to `mount_domains(app)`.
- Modify `app/services/artifacts.py` — add title/description length caps in `create_draft`.
- Modify `app/api/artifacts.py` — add `POST /html` (create-from-html), Author/Admin gate.
- Modify `eval/artifact_service_test.py` — length-cap checks.
- Modify `eval/artifact_rbac_test.py` — assert `POST /artifacts/html` requires Author/Admin.
- Create `eval/artifact_studio_test.py` — tool/state-mapping unit test (LLM never called) + mount-deps introspection.

**Frontend (`apps/frontend/`):**
- Modify `app/api/copilotkit/[[...slug]]/route.ts` — register `"artifacts-studio"` HttpAgent (resume bridge).
- Create `components/artifacts/LivePreview.tsx` — the sandbox iframe as a reusable component taking an `html` string; refactor `SandboxViewer.tsx` to reuse it.
- Create `components/artifacts/ArtifactStudio.tsx` + `app/artifacts/new/page.tsx` — the canvas.
- Create `app/api/artifacts/create/route.ts` — create-from-html proxy.
- Modify `components/artifacts/ArtifactsView.tsx` — inline form → "＋ New artifact" link.

**E2E:** add `e2e/artifacts-studio.spec.ts`.

---

## Chunk 1: Backend — Studio agent, mount, create-from-html, caps

### Task 1: `ArtifactDraft` + `update_artifact` tool + studio agent

**Files:**
- Create: `apps/backend/app/agents/artifacts_studio.py`
- Test: `apps/backend/eval/artifact_studio_test.py`

Mirror the per-request agent construction in `app/agents/platform.py:30-74` (verbatim reference): `FoundryChatClient(project_endpoint=cfg.foundry_project_endpoint or None, model=cfg.foundry_model, credential=credential_for_request())` → `client.as_agent(name=, description=, instructions=, tools=[update_artifact])`, wrapped in `PerRequestAgent(...)` (`app/agents/per_request.py`). `@tool` import: `from agent_framework import tool` (confirm against `app/tools/tickets.py`).

- [ ] **Step 1: Write the failing test** (`eval/artifact_studio_test.py`):

```python
"""Artifacts Studio agent — tool + state wiring (no LLM, no network).

Run (from apps/backend/):  uv run python -m eval.artifact_studio_test
"""
import sys


def main() -> int:
    failures: list[str] = []

    def check(name, cond):
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    from app.agents.artifacts_studio import ArtifactDraft, update_artifact

    # ArtifactDraft holds the complete HTML document.
    d = ArtifactDraft(html="<!doctype html><html><body>x</body></html>")
    check("ArtifactDraft.html round-trips", d.html.startswith("<!doctype html>"))

    # update_artifact is an agent-framework @tool (has the tool marker) and returns a confirmation.
    check("update_artifact is a tool", hasattr(update_artifact, "__agent_framework_tool__")
          or hasattr(update_artifact, "ai_function") or callable(update_artifact))

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
```

> The `@tool`-marker attribute name varies by version — the test uses a tolerant check. During implementation, run `python3 -c "from agent_framework import tool; ..."` to see the real marker and tighten the assertion if easy; otherwise the tolerant check is acceptable.

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_studio_test`
Expected: FAIL — `ModuleNotFoundError: No module named 'app.agents.artifacts_studio'`.

- [ ] **Step 3: Implement `app/agents/artifacts_studio.py`** (agent + tool + wrap; mount added in Task 2):

```python
"""HTML Artifacts Studio — a generative-UI agent that streams a self-contained HTML
document into AG-UI shared state (predictive), gated by an in-loop edit confirmation.

Mirrors app/agents/platform.py's per-request construction (FoundryChatClient.as_agent +
PerRequestAgent), plus the AG-UI shared-state wrapper (AgentFrameworkAgent with
state_schema/predict_state_config/require_confirmation — see docs/.../ag-ui/state-management).
"""
from __future__ import annotations

from agent_framework import tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_ag_ui import AgentFrameworkAgent
from pydantic import BaseModel, Field

from app.agents.per_request import PerRequestAgent
from app.core.auth import credential_for_request
from app.core.tenant import tenant_config

_STUDIO_INSTRUCTIONS = (
    "You are an expert front-end engineer authoring a SINGLE self-contained HTML document. "
    "To create or change the artifact you MUST call the `update_artifact` tool and pass the "
    "COMPLETE updated document in `artifact.html`, starting with <!doctype html>, with all CSS "
    "and JS inline and NO external requests — safe to render inside a sandboxed iframe. When the "
    "user asks for a change, include the ENTIRE document with the change applied; never return a "
    "diff or a partial, and never drop existing content. After calling the tool, reply with a "
    "one-sentence summary of what you did."
)


class ArtifactDraft(BaseModel):
    html: str = Field(..., description="The COMPLETE self-contained HTML document, starting with <!doctype html>.")


@tool
def update_artifact(artifact: ArtifactDraft) -> str:
    """Write the COMPLETE updated HTML document (never a diff/partial; keep all existing content)."""
    return "Artifact updated."


def build_studio_agent():
    cfg = tenant_config()
    client = FoundryChatClient(
        project_endpoint=cfg.foundry_project_endpoint or None,
        model=cfg.foundry_model,
        credential=credential_for_request(),
    )
    return client.as_agent(
        name="ArtifactsStudio",
        description="Conversationally generates and refines a self-contained HTML artifact.",
        instructions=_STUDIO_INSTRUCTIONS,
        tools=[update_artifact],
    )


# Per-request proxy (rebuilds per run so shared mode reads the request's tenant config), wrapped in
# the AG-UI shared-state adapter: the artifact.html field streams via STATE_DELTA as the model
# generates the tool argument, and require_confirmation gates each edit before it's applied.
studio_agent = AgentFrameworkAgent(
    agent=PerRequestAgent(
        "artifacts-studio", build_studio_agent,
        name="ArtifactsStudio",
        description="Conversationally generates and refines a self-contained HTML artifact.",
    ),
    name="ArtifactsStudio",
    description="Conversationally generates and refines a self-contained HTML artifact.",
    state_schema={"artifact": {"type": "object", "description": "The current HTML artifact draft"}},
    predict_state_config={"artifact": {"tool": "update_artifact", "tool_argument": "artifact"}},
    require_confirmation=True,
)
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_studio_test`
Expected: PASS. Also confirm the module imports without a live tenant: `uv run python -c "import app.agents.artifacts_studio as s; print(type(s.studio_agent).__name__)"` → `AgentFrameworkAgent` (constructing `studio_agent` must NOT call the LLM or read a live tenant — `PerRequestAgent` defers the build, so this is safe; if `AgentFrameworkAgent()` eagerly touches the inner agent, report it as BLOCKED).

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/agents/artifacts_studio.py apps/backend/eval/artifact_studio_test.py
git commit -m "feat(artifacts): Studio agent — update_artifact tool + AG-UI shared/predictive state"
```

---

### Task 2: Mount `/artifacts-studio` (auth Author/Admin)

**Files:**
- Modify: `apps/backend/app/agents/artifacts_studio.py` (add `mount_artifacts_studio`)
- Modify: `apps/backend/app/main.py:49` (call it after `mount_domains(app)`)
- Test: `apps/backend/eval/artifact_studio_test.py` (extend — introspect the mount deps)

Mirror `app/domains.py::_mount_platform` (`add_agent_framework_fastapi_endpoint(app, agent=..., path=..., dependencies=...)`). The dep list is `[*auth_dependencies(), Depends(require_role("Author","Admin"))]`.

- [ ] **Step 1: Extend the test** — fake the adapter, call the mount, assert the path + that a dep carries the `_required_roles={"Author","Admin"}` tag:

```python
    # --- mount introspection: /artifacts-studio gated Author/Admin ---
    import app.agents.artifacts_studio as studio_mod
    import app.core.settings as settings_mod
    settings_mod.settings.entra_tenant_id = "t"       # force auth ON so deps attach
    settings_mod.settings.entra_api_client_id = "c"

    calls = []
    orig = studio_mod.add_agent_framework_fastapi_endpoint
    studio_mod.add_agent_framework_fastapi_endpoint = (
        lambda app, agent=None, path=None, dependencies=None, **kw:
        calls.append({"path": path, "dependencies": dependencies or []})
    )
    try:
        studio_mod.mount_artifacts_studio(object())  # fake app; adapter is faked
    finally:
        studio_mod.add_agent_framework_fastapi_endpoint = orig

    check("studio mounted at /artifacts-studio", any(c["path"] == "/artifacts-studio" for c in calls))
    roles = set()
    for c in calls:
        for dep in c["dependencies"]:
            roles |= getattr(getattr(dep, "dependency", None), "_required_roles", set())
    check("studio mount requires Author/Admin", {"Author", "Admin"} <= roles)
```

> `Depends(x)` stores the callable on `.dependency`; `require_role` tags it with `_required_roles` (added in the MVP Chunk 4). Verify this attribute path during implementation and adjust if the FastAPI version exposes it differently.

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_studio_test`
Expected: FAIL — `AttributeError: module 'app.agents.artifacts_studio' has no attribute 'mount_artifacts_studio'`.

- [ ] **Step 3: Add the import + mount function** to `app/agents/artifacts_studio.py`:

```python
from agent_framework_ag_ui import AgentFrameworkAgent, add_agent_framework_fastapi_endpoint  # extend the existing import
from fastapi import Depends, FastAPI

from app.core.auth import auth_dependencies, require_role


def mount_artifacts_studio(app: FastAPI) -> None:
    """POST /artifacts-studio — the AG-UI shared-state canvas agent, gated Author/Admin
    (mirror app/domains.py::_mount_platform's dependencies=... shape)."""
    add_agent_framework_fastapi_endpoint(
        app,
        agent=studio_agent,
        path="/artifacts-studio",
        dependencies=[*auth_dependencies(), Depends(require_role("Author", "Admin"))],
    )
```

- [ ] **Step 4: Call it in `app/main.py`** right after `mount_domains(app)` (line ~49):

```python
from app.agents.artifacts_studio import mount_artifacts_studio  # top-of-file import
...
mount_domains(app)
mount_artifacts_studio(app)
```

- [ ] **Step 5: Run to verify it passes + app imports**

Run: `cd apps/backend && uv run python -m eval.artifact_studio_test`
Expected: PASS.
Run: `cd apps/backend && ARTIFACT_STORE_BACKEND=memory uv run python -c "from app.main import app; print(any(getattr(r,'path','')=='/artifacts-studio' for r in app.routes))"`
Expected: prints `True` (needs `FOUNDRY_PROJECT_ENDPOINT` in env like other app.main imports; if it errors on that pre-existing requirement, note it — it's unrelated).

- [ ] **Step 6: Commit**

```bash
git add apps/backend/app/agents/artifacts_studio.py apps/backend/app/main.py apps/backend/eval/artifact_studio_test.py
git commit -m "feat(artifacts): mount /artifacts-studio AG-UI endpoint (Author/Admin gated)"
```

---

### Task 3: Length caps in `create_draft`

**Files:**
- Modify: `apps/backend/app/services/artifacts.py` (`create_draft`)
- Test: `apps/backend/eval/artifact_service_test.py` (extend)

`create_draft` real signature (from `app/services/artifacts.py`): `create_draft(*, tenant_id, title, description, type, html, user)` — raises `ValueError` on bad type / `validate_html`. Add caps at the top.

- [ ] **Step 1: Extend `eval/artifact_service_test.py`** (reuse its `_raises_value` helper + injected in-memory stores):

```python
    check("title over 200 rejected", _raises_value(lambda: svc.create_draft(
        tenant_id="t1", title="x" * 201, description="", type="report",
        html="<html><body>ok</body></html>", user=U())))
    check("description over 1000 rejected", _raises_value(lambda: svc.create_draft(
        tenant_id="t1", title="ok", description="y" * 1001, type="report",
        html="<html><body>ok</body></html>", user=U())))
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: FAIL (oversize title/description currently accepted).

- [ ] **Step 3: Add caps** at the top of `create_draft` (after the `type` check, before `validate_html`):

```python
    if len(title) > 200:
        raise ValueError("title exceeds 200 characters")
    if len(description) > 1000:
        raise ValueError("description exceeds 1000 characters")
```

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_service_test`
Expected: PASS (plus all prior checks).

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/services/artifacts.py apps/backend/eval/artifact_service_test.py
git commit -m "feat(artifacts): cap title/description length in create_draft"
```

---

### Task 4: `POST /artifacts/html` create-from-html route

**Files:**
- Modify: `apps/backend/app/api/artifacts.py`
- Test: `apps/backend/eval/artifact_rbac_test.py` (extend)

Mirror the existing router idioms in `app/api/artifacts.py`: `_author = Depends(require_role("Author","Admin"))`, `_dto(rec)`, `current_user()`, `artifact_tenant_id()`, `svc` + `HTTPException` mapping (`ValueError → 422`). Add a `CreateBody` model and the route.

- [ ] **Step 1: Extend `eval/artifact_rbac_test.py`** — add:

```python
    check("create-from-html requires Author/Admin",
          _roles_for("/artifacts/html", "POST") == {"Author", "Admin"})
```

- [ ] **Step 2: Run to verify it fails**

Run: `cd apps/backend && uv run python -m eval.artifact_rbac_test`
Expected: FAIL — `POST /artifacts/html` returns `set()` (route absent).

- [ ] **Step 3: Add the model + route** to `app/api/artifacts.py`:

```python
class CreateBody(BaseModel):
    title: str
    description: str = ""
    type: str = "report"
    html: str


@router.post("/html", dependencies=[_author])
def create_route(body: CreateBody) -> dict:
    try:
        rec = svc.create_draft(
            tenant_id=artifact_tenant_id(), title=body.title, description=body.description,
            type=body.type, html=body.html, user=current_user(),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _dto(rec)
```

> Route ordering: FastAPI matches in declaration order. `POST /html` must not shadow `POST /html/generate`. They differ by path (`/html` vs `/html/generate`), so order is fine — but place `create_route` near `generate_route` for readability and re-run the RBAC test to confirm both resolve.

- [ ] **Step 4: Run to verify it passes**

Run: `cd apps/backend && uv run python -m eval.artifact_rbac_test && uv run python -m eval.artifact_service_test && uv run python -m eval.artifact_studio_test`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add apps/backend/app/api/artifacts.py apps/backend/eval/artifact_rbac_test.py
git commit -m "feat(artifacts): POST /artifacts/html — create draft from provided HTML (Author/Admin)"
```

---

## Chunk 2: Frontend — canvas

### Task 5: Register the Studio agent in the CopilotKit runtime

**Files:**
- Modify: `apps/frontend/app/api/copilotkit/[[...slug]]/route.ts`

The Studio is a **bespoke** agent (not a `/d/[domain]` registry domain), so register it manually beside the hosted twins (mirror `helpdeskHosted`/`platformHosted`). It carries `require_confirmation` interrupts → use `withResumeBridge`.

- [ ] **Step 1: Add the URL + agent** (near the hosted-twin consts and the `runtime` agents map):

```ts
const ARTIFACTS_STUDIO_AGUI_URL =
  process.env.ARTIFACTS_STUDIO_AGUI_URL ?? `${BACKEND}/artifacts-studio`;
const artifactsStudio = withResumeBridge(ARTIFACTS_STUDIO_AGUI_URL);
```

and in `new CopilotRuntime({ agents: { ... } })`:

```ts
  agents: {
    ...registryAgents,
    "helpdesk-hosted": helpdeskHosted,
    "platform-hosted": platformHosted,
    "artifacts-studio": artifactsStudio,
  },
```

- [ ] **Step 2: Verify typecheck + build**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: clean. (Build verified after the canvas exists in Task 7.)

- [ ] **Step 3: Commit**

```bash
git add "apps/frontend/app/api/copilotkit/[[...slug]]/route.ts"
git commit -m "feat(artifacts): register artifacts-studio agent in CopilotKit runtime (resume bridge)"
```

---

### Task 6: Extract a reusable `LivePreview` sandbox component

**Files:**
- Create: `apps/frontend/components/artifacts/LivePreview.tsx`
- Modify: `apps/frontend/components/artifacts/SandboxViewer.tsx` (reuse it)

`LivePreview` renders the sandbox iframe from an `html` string (no fetching). `SandboxViewer` keeps its fetch-by-id behavior but renders through `LivePreview`. Preserve the security invariant EXACTLY: `sandbox="allow-scripts"`, no `allow-same-origin`, `srcDoc`.

- [ ] **Step 1: Create `LivePreview.tsx`:**

```tsx
"use client";

// Sandboxed HTML preview. SECURITY: sandbox="allow-scripts" WITHOUT allow-same-origin
// (opaque origin) — the content cannot read the app's token/DOM. Do NOT add allow-same-origin.
export function LivePreview({ html, title = "artifact-preview" }: { html: string; title?: string }) {
  return (
    <iframe
      title={title}
      srcDoc={html}
      sandbox="allow-scripts"
      style={{ width: "100%", height: "70vh", border: "1px solid var(--border)", borderRadius: 12 }}
    />
  );
}
```

- [ ] **Step 2: Refactor `SandboxViewer.tsx`** to render `<LivePreview html={html} />` in its success branch (keep the fetch/loading/error logic; drop the inline `<iframe>`).

- [ ] **Step 3: Verify typecheck**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/components/artifacts/LivePreview.tsx apps/frontend/components/artifacts/SandboxViewer.tsx
git commit -m "refactor(artifacts): extract LivePreview sandbox iframe (shared by viewer + studio)"
```

---

### Task 7: `ArtifactStudio` canvas + `/artifacts/new` page

**Files:**
- Create: `apps/frontend/components/artifacts/ArtifactStudio.tsx`
- Create: `apps/frontend/app/artifacts/new/page.tsx`

Build on the repo's real v2 pattern — copy the shapes from `components/chat/HelpdeskApp.tsx` (provider + token), `WorkflowSteps.tsx` (`useAgent` + `agent.subscribe`), and `TicketApproval.tsx` (interrupt tap + `runAgent({resume})`). Read those three files first.

Key wiring:
- Provider: `<CopilotKitProvider runtimeUrl="/api/copilotkit" headers={authorization ? { Authorization: authorization } : undefined}>` — get `authorization` via `acquireTokenSilent` exactly as `HelpdeskApp.tsx` does (or `undefined` locally when auth is off).
- `const { agent } = useAgent({ agentId: "artifacts-studio" })` from `@copilotkit/react-core/v2`.
- **Live HTML:** `agent.subscribe({ onStateSnapshotEvent, onStateDeltaEvent })` → maintain an `html` React state. Snapshot: read `event.snapshot.artifact.html`. Delta: apply the JSON-Patch on `/artifact` (the value replaces `artifact`; read `.html`). If the installed version also exposes `agent.state`, reading `agent.state.artifact?.html` on each `onEvent` is an acceptable simpler equivalent — verify which is populated and use it; keep the subscribe tap as the guaranteed path. Throttle `setHtml` with `requestAnimationFrame`.
- **Edit approval:** in `agent.subscribe({ onEvent })`, detect the confirmation event. Per `agent_framework_ag_ui` rc5, `require_confirmation` emits a `CustomEvent(name="function_approval_request")` (the workflow HITL uses `request_info`). **Handle BOTH names** and, like `TicketApproval.tsx`, resolve with `agent.runAgent({ resume: [{ interruptId: id, status: "resolved", payload: approved }] })`. The exact event field names + payload are **verified live in the E2E** (Task 11) — capture the real event and adjust the discriminator (mirror TicketApproval's `#3199` note).
- Layout: two columns — `<CopilotChat agentId="artifacts-studio" />` left; right = Title input + Type select + `<LivePreview html={html} />` + an inline approval card (reuse `TicketApproval`'s card styles) + **Save as draft**.
- **Save:** `authedFetch("/api/artifacts/create", { method:"POST", headers:{"Content-Type":"application/json"}, body: JSON.stringify({ title, type, html }) })` → on `ok`, `router.push(\`/artifacts/${(await r.json()).id}\`)`.

- [ ] **Step 1: Read the three reference files** (`HelpdeskApp.tsx`, `WorkflowSteps.tsx`, `TicketApproval.tsx`) and write `ArtifactStudio.tsx` following their idioms. Implement validations inline (Task 10 lists the exact rules — do them here to avoid a second pass): Title required ≤200, chat input handled by CopilotChat, **Save** disabled unless `title && type && html`.

- [ ] **Step 2: Create `app/artifacts/new/page.tsx`:**

```tsx
import { AppShell } from "@/components/shell/AppShell";
import { ArtifactStudio } from "@/components/artifacts/ArtifactStudio";

export default function NewArtifactPage() {
  return (
    <AppShell>
      <ArtifactStudio />
    </AppShell>
  );
}
```

- [ ] **Step 3: Verify typecheck + build**

Run: `cd apps/frontend && npx tsc --noEmit && npm run build`
Expected: both succeed (route `/artifacts/new` compiles). If build rewrites `tsconfig.json`/`next-env.d.ts`, `git checkout --` them (don't commit).

- [ ] **Step 4: Commit**

```bash
git add apps/frontend/components/artifacts/ArtifactStudio.tsx apps/frontend/app/artifacts/new/page.tsx
git commit -m "feat(artifacts): Artifacts Studio canvas — live streamed preview + in-loop edit approval"
```

---

### Task 8: Create-from-html proxy

**Files:**
- Create: `apps/frontend/app/api/artifacts/create/route.ts`

Mirror the existing generate proxy in `app/api/artifacts/route.ts` (forward `Authorization`, POST body passthrough, 502 fail-soft). A separate `/create` path avoids touching the existing `POST /api/artifacts` (which proxies to `/generate`).

- [ ] **Step 1: Create the route:**

```ts
import { NextRequest, NextResponse } from "next/server";

export const dynamic = "force-dynamic";
const BACKEND = process.env.BACKEND_URL ?? "http://localhost:8000";

export async function POST(req: NextRequest) {
  try {
    const auth = req.headers.get("authorization");
    const r = await fetch(`${BACKEND}/artifacts/html`, {
      method: "POST",
      cache: "no-store",
      headers: { "Content-Type": "application/json", ...(auth ? { Authorization: auth } : {}) },
      body: await req.text(),
    });
    return new NextResponse(await r.text(), {
      status: r.status,
      headers: { "Content-Type": "application/json" },
    });
  } catch {
    return NextResponse.json({ error: "backend unreachable" }, { status: 502 });
  }
}
```

- [ ] **Step 2: Verify typecheck**

Run: `cd apps/frontend && npx tsc --noEmit`
Expected: clean.

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/app/api/artifacts/create/route.ts
git commit -m "feat(artifacts): create-from-html proxy (POST /api/artifacts/create → backend)"
```

---

### Task 9: List page → "＋ New artifact"

**Files:**
- Modify: `apps/frontend/components/artifacts/ArtifactsView.tsx`

Replace the inline "Generate HTML artifact" `<section className="card">…</section>` block (and the now-unused `title`/`prompt`/`type`/`busy`/`generate` state) with a header link to `/artifacts/new`. Keep the list/table + `load()` intact.

- [ ] **Step 1: Replace the generate section** with a link/button:

```tsx
import Link from "next/link";
// …in the header row, next to Refresh:
<Link className="btn btn-solid" href="/artifacts/new">＋ New artifact</Link>
```

Remove the generate-form JSX and its unused state/handlers (keep `items`, `error`, `load`).

- [ ] **Step 2: Verify typecheck + build**

Run: `cd apps/frontend && npx tsc --noEmit && npm run build`
Expected: clean (no unused-var errors — remove all now-dead state).

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/components/artifacts/ArtifactsView.tsx
git commit -m "feat(artifacts): list page opens the Studio (＋ New artifact) instead of inline form"
```

---

## Chunk 3: Validations recap, E2E, verification

### Task 10: Confirm client validations (implemented in Task 7)

**Files:** `apps/frontend/components/artifacts/ArtifactStudio.tsx` (verify)

- [ ] **Step 1:** Confirm by inspection (and adjust if missing): Title `maxLength={200}` + required; **Save as draft** `disabled={!title || !type || !html || saving}`; a `muted` inline message when a save fails (mirror `ArtifactDetail`'s error banner). Re-run `npx tsc --noEmit`.
- [ ] **Step 2: Commit** any fixes: `git commit -am "fix(artifacts): studio client validations (title cap, save gating, error banner)"` (with trailer).

---

### Task 11: Playwright E2E — Studio flow

**Files:**
- Create: `apps/frontend/e2e/artifacts-studio.spec.ts`

Local auth-off, real Foundry generation. This is also where the **live event-shape verification** happens: if the approval card never appears, capture the AG-UI events and fix the discriminator in `ArtifactStudio.tsx` (Task 7), then re-run.

- [ ] **Step 1: Write the spec** (mirror `e2e/artifacts.spec.ts` structure — screenshots to `artifacts/steps-studio/`):

```ts
import { test, expect } from "@playwright/test";

test("studio: describe → live preview → confirm edit → save → draft", async ({ page }) => {
  await page.goto("/artifacts/new");
  await expect(page.getByRole("heading", { name: /studio|new artifact|artifacts/i })).toBeVisible({ timeout: 30_000 });

  // Send a prompt in the CopilotKit chat.
  const input = page.getByRole("textbox").first();
  await input.fill("Create a one-page HTML report titled 'Studio Smoke' with an <h1> and one paragraph.");
  await input.press("Enter");

  // Live preview iframe appears and eventually renders the heading.
  const iframe = page.locator('iframe[title="artifact-preview"]');
  await expect(iframe).toBeVisible({ timeout: 120_000 });
  const sandbox = await iframe.getAttribute("sandbox");
  expect(sandbox).toBe("allow-scripts");

  // In-loop edit confirmation (require_confirmation) — approve it.
  await page.getByRole("button", { name: /approve|apply/i }).click({ timeout: 120_000 });

  // Set metadata + save.
  await page.getByPlaceholder(/title/i).fill("Studio Smoke " + Date.now());
  await page.getByRole("button", { name: /save as draft/i }).click();

  // Landed on the detail page as a draft.
  await expect(page.locator(".pill", { hasText: "draft" })).toBeVisible({ timeout: 30_000 });
});
```

> Selectors are approximate — adjust to the real DOM after Task 7. If the approval button text/flow differs, this test is what surfaces it.

- [ ] **Step 2: Run it** against the running local servers (start them per the MVP runbook if needed: backend `:8010` auth-off + `ARTIFACT_STORE_BACKEND=memory`, frontend `:3010` with `BACKEND_URL=http://localhost:8010` and `ARTIFACTS_STUDIO_AGUI_URL=http://localhost:8010/artifacts-studio`):

Run: `cd apps/frontend/e2e && E2E_BASE_URL=http://localhost:3010 npx playwright test artifacts-studio.spec.ts --reporter=list`
Expected: 1 passed. If the approval step hangs, inspect the captured trace/events, fix the event discriminator in `ArtifactStudio.tsx`, re-run.

- [ ] **Step 3: Commit**

```bash
git add apps/frontend/e2e/artifacts-studio.spec.ts
git commit -m "test(artifacts): Playwright E2E for the Studio (generate → confirm → save → draft)"
```

---

### Task 12: Full verification

- [ ] Backend suite green: `cd apps/backend && uv run python -m eval.artifact_store_test && uv run python -m eval.artifact_service_test && uv run python -m eval.artifact_rbac_test && uv run python -m eval.artifact_studio_test`.
- [ ] Wire `eval.artifact_studio_test` into `.github/workflows/ci.yml`'s artifact-tests step (alongside the other three).
- [ ] Frontend: `cd apps/frontend && npx tsc --noEmit && npm run build` clean; `tsconfig.json`/`next-env.d.ts` reverted (not committed).
- [ ] Studio E2E green (Task 11); MVP E2E (`e2e/artifacts.spec.ts`) still green.
- [ ] Manual smoke (use @verify / @run): open `/artifacts` → "＋ New artifact" → describe → preview streams live → approve an edit → refine → approve → Save as draft → detail shows `draft` → request-approval → approve → `published` + hash. Inspect the studio iframe: `sandbox="allow-scripts"`, no `allow-same-origin`.
- [ ] Security review: `@security-review` on the branch (untrusted-HTML + a new AG-UI endpoint).

---

## Definition of done

- [ ] Backend: `/artifacts-studio` mounted (Author/Admin), `POST /artifacts/html` create-from-html, length caps — all four eval modules green + wired into CI.
- [ ] Frontend: `/artifacts/new` Studio streams the HTML live into the sandbox, shows the in-loop approval card, saves a draft; list opens the Studio; typecheck + build clean.
- [ ] Studio Playwright E2E green; the approval event discriminator verified against the real AG-UI stream.
- [ ] Security invariant intact (`LivePreview`/`SandboxViewer`: `allow-scripts`, no `allow-same-origin`).
- [ ] The two approvals stay distinct (canvas edit-confirm vs lifecycle publish).

## Notes for the executor

- **CLAUDE.md rule #1:** Task 1's agent construction is copied from `app/agents/platform.py`; the `AgentFrameworkAgent(state_schema, predict_state_config, require_confirmation)` surface is verified in rc5. If `agent.subscribe` state-event hooks or the `function_approval_request` shape differ live, adjust per the real AG-UI stream (Task 11) — do not guess silently; the mechanism (resume bridge) is proven by `TicketApproval.tsx`.
- **Frontend is E2E-verified, not unit-tested** — the repo has no React test harness; `tsc`/`build`/Playwright are the gates.
- **Deprecation of the one-shot form is UI-only** — `POST /artifacts/html/generate` stays for the MVP E2E and headless use.
