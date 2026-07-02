"""Platform/ops domain — a TOOL-driven agent (not KB-grounded).

Unlike the grounded experts (cockpit/selfwiki), this agent's capability is the set of
Microsoft first-party MCP tools assembled per-request from app/agents/mcp/. Tools are
role-filtered (Reader sees reads, Author/Admin see writes) and, for OBO servers, run as the
signed-in user. The /platform endpoint requires sign-in; the per-request tool build reads the
caller's roles + OBO credential from the request context (set by the auth dependency).

APIs mirror app/agents/selfwiki.py (agent-framework 1.9.0).
"""

from __future__ import annotations

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient

from app.agents.mcp.tools import build_mcp_tools
from app.agents.per_request import PerRequestAgent
from app.agents.prompts import PLATFORM_INSTRUCTIONS
from app.core.auth import credential_for_request
from app.core.settings import settings  # platform-global (mcp_enabled)
from app.core.tenant import tenant_config  # per-tenant (foundry endpoint/model)


def platform_configured() -> bool:
    if settings.deployment_mode == "shared":
        return bool(settings.mcp_enabled)  # shared: mount if MCP globally on; per-tenant gated at request time
    return bool(settings.mcp_enabled and tenant_config().foundry_project_endpoint)


def build_platform_agent() -> Agent:
    """A tool-driven concierge over the Microsoft first-party MCP servers."""
    cfg = tenant_config()
    client = FoundryChatClient(
        project_endpoint=cfg.foundry_project_endpoint or None,
        model=cfg.foundry_model,
        credential=credential_for_request(),
    )
    return client.as_agent(
        name="PlatformConcierge",
        description="Engineering-platform concierge over Microsoft first-party MCP tools.",
        instructions=PLATFORM_INSTRUCTIONS,
        tools=build_mcp_tools(),
    )


# The platform endpoint's serving object: the generic per-request proxy (app/agents/per_request.py)
# rebuilds `build_platform_agent()` on every `.run()`, so each request gets tools filtered by the
# CURRENT caller's roles + OBO credential. `add_agent_framework_fastapi_endpoint(agent=...)` wants a
# `SupportsAgentRun` *instance*, not a factory — the proxy IS that instance. The name/description
# overrides advertise the platform identity (the generic default would be "platform").
platform_agent_proxy = PerRequestAgent(
    "platform", build_platform_agent,
    name="PlatformConcierge",
    description="Engineering-platform concierge over Microsoft first-party MCP tools.",
)
