"""HTML Artifacts Studio — a generative-UI agent that streams a self-contained HTML
document into AG-UI shared state (predictive), gated by an in-loop edit confirmation.

Mirrors app/agents/platform.py's per-request construction (FoundryChatClient.as_agent +
PerRequestAgent), plus the AG-UI shared-state wrapper (AgentFrameworkAgent with
state_schema/predict_state_config/require_confirmation — see docs/.../ag-ui/state-management).
"""
from __future__ import annotations

from pathlib import Path

from agent_framework import SkillsProvider, tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_ag_ui import AgentFrameworkAgent, add_agent_framework_fastapi_endpoint
from fastapi import Depends, FastAPI

from app.agents.mcp.tools import build_artifact_mcp_reads
from app.agents.per_request import PerRequestAgent
from app.core.auth import auth_dependencies, credential_for_request, require_role
from app.core.settings import settings
from app.core.tenant import tenant_config

_SKILLS_DIR = Path(__file__).resolve().parents[2] / "artifact-skills"  # apps/backend/artifact-skills

_STUDIO_INSTRUCTIONS = (
    "You are an expert front-end engineer authoring a SINGLE self-contained HTML document. "
    "Choose the skill that best matches the requested artifact; if the user pinned a skill, use "
    "it. Follow its SKILL.md via load_skill/read_skill_resource. To create or change the artifact "
    "you MUST call the `update_artifact` tool and pass the COMPLETE updated document in `html`, "
    "starting with <!doctype html>, with all CSS and JS inline and NO external requests — safe to "
    "render inside a sandboxed iframe. When the user asks for a change, include the ENTIRE "
    "document with the change applied; never return a diff or a partial, and never drop existing "
    "content. Call `update_artifact` with the complete `html`, a concise `title`, a `type` from "
    "{report,presentation,walkthrough,dashboard}, and the `skill` you used. Use the read-only data "
    "tools only when the user asks for data-grounded content. After calling the tool, reply with a "
    "one-sentence summary of what you did."
)


@tool(approval_mode="always_require")
def update_artifact(html: str, title: str, type: str, skill: str) -> str:
    """Write the COMPLETE artifact: the full HTML document (html), a concise title, a type
    (one of report|presentation|walkthrough|dashboard), and the skill name you used.

    `approval_mode="always_require"` makes the agent emit a `function_approval_request` content
    for each call, which the AG-UI adapter surfaces as the in-loop edit-confirmation event (paired
    with the agent's `require_confirmation=True`). Without it the tool executes directly and no
    approval interrupt is emitted (verified live — see docs/.../plans/2026-07-06-artifacts-canvas.md).
    """
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
        context_providers=[SkillsProvider.from_paths(str(_SKILLS_DIR))],  # no script_runner (no shell)
        tools=[update_artifact, *build_artifact_mcp_reads()],
    )


# Per-request proxy (rebuilds per run so shared mode reads the request's tenant config), wrapped in
# the AG-UI shared-state adapter: the `html` field streams via STATE_DELTA as the model generates
# the tool argument, and require_confirmation gates each edit before it's applied. The mapped tool
# argument MUST be a flat string — the predictive partial-delta extractor only streams string args
# (regex `"arg":\s*"([^"]*)`); a nested-object arg would emit a single state event at the end (no
# live streaming). Mirrors the shipped document_writer_agent.py example.
studio_agent = AgentFrameworkAgent(
    agent=PerRequestAgent(
        "artifacts-studio", build_studio_agent,
        name="ArtifactsStudio",
        description="Conversationally generates and refines a self-contained HTML artifact.",
    ),
    name="ArtifactsStudio",
    description="Conversationally generates and refines a self-contained HTML artifact.",
    # Only `html` is shared state (predictive live preview). title/type/skill are NOT state —
    # they're read from the function_approval_request arguments in the frontend (see the comment
    # on predict_state_config below; verified live in Step 4b).
    state_schema={"html": {"type": "string", "description": "The current HTML artifact document"}},
    # html only — predictive streaming for the live preview. VERIFIED LIVE (Step 4b probe):
    # a state_schema key WITHOUT a predict_state_config entry stays an empty {} in state (title/
    # type/skill are NOT populated via state). Their values DO arrive in the
    # function_approval_request event's function_call.arguments ({html,title,type,skill}), so the
    # frontend reads title/type/skill from that approval event (option c) — no backend change.
    # Keeping html-only here avoids partial-streaming the short fields for no benefit.
    predict_state_config={"html": {"tool": "update_artifact", "tool_argument": "html"}},
    require_confirmation=True,
)


def studio_configured() -> bool:
    """Mirror app/agents/platform.py::platform_configured: in shared mode mount globally (per-request
    auth gates it); in self_hosted/dedicated require a Foundry endpoint so we don't expose a 500-ing
    endpoint in a Foundry-less env."""
    if settings.deployment_mode == "shared":
        return True
    return bool(tenant_config().foundry_project_endpoint)


def mount_artifacts_studio(app: FastAPI) -> None:
    """POST /artifacts-studio — the AG-UI shared-state canvas agent, gated Author/Admin
    (mirror app/domains.py::_mount_platform's dependencies=... shape).

    Deliberately NOT tenant-entitlement-gated (no shared-mode require_domain): the Studio is a
    cross-cutting Author/Admin authoring tool, not a licensed /d/[domain] domain (ADR-010)."""
    if not studio_configured():
        return
    add_agent_framework_fastapi_endpoint(
        app,
        agent=studio_agent,
        path="/artifacts-studio",
        dependencies=[*auth_dependencies(), Depends(require_role("Author", "Admin"))],
    )
