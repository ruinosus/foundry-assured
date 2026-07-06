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
from pydantic import BaseModel, Field

from app.agents.per_request import PerRequestAgent
from app.core.auth import auth_dependencies, credential_for_request, require_role
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


def mount_artifacts_studio(app: FastAPI) -> None:
    """POST /artifacts-studio — the AG-UI shared-state canvas agent, gated Author/Admin
    (mirror app/domains.py::_mount_platform's dependencies=... shape)."""
    add_agent_framework_fastapi_endpoint(
        app,
        agent=studio_agent,
        path="/artifacts-studio",
        dependencies=[*auth_dependencies(), Depends(require_role("Author", "Admin"))],
    )
