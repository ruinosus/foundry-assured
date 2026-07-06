"""HTML Artifacts Studio — a generative-UI agent that streams a self-contained HTML
document into AG-UI shared state (predictive), gated by an in-loop edit confirmation.

Mirrors app/agents/platform.py's per-request construction (FoundryChatClient.as_agent +
PerRequestAgent), plus the AG-UI shared-state wrapper (AgentFrameworkAgent with
state_schema/predict_state_config/require_confirmation — see docs/.../ag-ui/state-management).
"""
from __future__ import annotations

from agent_framework import tool
from agent_framework.foundry import FoundryChatClient
from agent_framework_ag_ui import AgentFrameworkAgent, add_agent_framework_fastapi_endpoint
from fastapi import Depends, FastAPI

from app.agents.per_request import PerRequestAgent
from app.core.auth import auth_dependencies, credential_for_request, require_role
from app.core.settings import settings
from app.core.tenant import tenant_config

_STUDIO_INSTRUCTIONS = (
    "You are an expert front-end engineer authoring a SINGLE self-contained HTML document. "
    "To create or change the artifact you MUST call the `update_artifact` tool and pass the "
    "COMPLETE updated document in `html`, starting with <!doctype html>, with all CSS "
    "and JS inline and NO external requests — safe to render inside a sandboxed iframe. When the "
    "user asks for a change, include the ENTIRE document with the change applied; never return a "
    "diff or a partial, and never drop existing content. After calling the tool, reply with a "
    "one-sentence summary of what you did."
)


@tool(approval_mode="always_require")
def update_artifact(html: str) -> str:
    """Write the COMPLETE updated HTML document (never a diff/partial; keep all existing content).

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
        tools=[update_artifact],
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
    state_schema={"html": {"type": "string", "description": "The current HTML artifact document"}},
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
