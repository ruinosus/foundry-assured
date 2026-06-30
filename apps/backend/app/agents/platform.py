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


class PerRequestPlatformAgent:
    """A `SupportsAgentRun` proxy that REBUILDS the platform agent on every call, so each
    request gets tools filtered by the CURRENT caller's roles + OBO credential (read from the
    request-context contextvar set by the auth dependency).

    Why this exists: `add_agent_framework_fastapi_endpoint(agent=...)` wants a
    `SupportsAgentRun` *instance*, not a factory function. The grounded domains build once at
    boot under `DefaultAzureCredential` — we can't, because the whole point of this agent is
    per-request identity/role filtering. The helpdesk path solves the same problem with a
    `Workflow` subclass factory; a single agent needs this lighter proxy instead.

    `SupportsAgentRun` is a `@runtime_checkable` Protocol whose members are
    `run`/`create_session`/`get_session` AND the data attributes `id`/`name`/`description`
    — `isinstance` enforces the attributes too, so the three methods ALONE fail the check and
    registration raises `TypeError`. Hence the class attributes below. The `run` delegation is
    the live path; `create_session`/`get_session` exist only to satisfy the protocol (the AG-UI
    adapter builds its own `AgentSession` and never calls them on the default
    `use_service_session=False` path), so they delegate but carry no session state.
    """

    id = "platform"
    name = "PlatformConcierge"
    description = "Engineering-platform concierge over Microsoft first-party MCP tools."

    def run(self, *args, **kwargs):  # returns Awaitable | ResponseStream — pass through
        return build_platform_agent().run(*args, **kwargs)

    def create_session(self, *args, **kwargs):  # protocol-only (see docstring)
        return build_platform_agent().create_session(*args, **kwargs)

    def get_session(self, *args, **kwargs):  # protocol-only (see docstring)
        return build_platform_agent().get_session(*args, **kwargs)
