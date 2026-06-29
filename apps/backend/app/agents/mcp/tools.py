"""Build live framework MCP tools from the registry for the CURRENT request.

Internal path only (MCPStreamableHTTPTool). Per server, filter tools to the caller's role
(registry.visible_tools), then construct the tool with:
  - allowed_tools = the visible read + write tool names (so the model can't call hidden ones)
  - approval_mode = "never_require" — native MCP approval does NOT execute over AG-UI
    (agent-framework #3199), so write approval is handled by OUR HITL card in the workflow,
    not here. We still gate WRITE visibility by role above; a Reader simply never sees a write.
  - header_provider = a callable that injects the per-user OBO bearer for auth="obo" servers
    (lazy: evaluated at call time with the request's credential). Public servers get none.

GitHub (auth="github_pat") and hosted OAuth-passthrough are handled in later chunks; this
builder covers public + obo. Unknown auth → server skipped (fail-closed).
"""

from __future__ import annotations

from agent_framework import MCPStreamableHTTPTool

from app.agents.mcp.registry import McpServer, enabled_servers, visible_tools
from app.core.auth import credential_for_request, current_roles
from app.core.settings import settings


def _obo_header_provider(scope: str):
    """A header_provider that mints a fresh OBO bearer for the signed-in user at call time."""
    def provider(_existing: dict) -> dict:
        token = credential_for_request().get_token(scope)
        return {"Authorization": f"Bearer {token.token}"}
    return provider


def _build_one(server: McpServer, roles: set[str]) -> MCPStreamableHTTPTool | None:
    reads, writes = visible_tools(server, roles)
    allowed = reads + writes
    if not allowed:
        return None  # caller sees no tools on this server
    kwargs: dict = {
        "name": f"mcp_{server.id}",
        "url": server.url,
        "allowed_tools": allowed,
        "approval_mode": "never_require",  # see module docstring (HITL handles writes)
    }
    if server.auth == "obo" and server.obo_scope:
        kwargs["header_provider"] = _obo_header_provider(server.obo_scope)
    elif server.auth != "public":
        return None  # github_pat / oauth_passthrough handled elsewhere
    return MCPStreamableHTTPTool(**kwargs)


def build_mcp_tools() -> list[MCPStreamableHTTPTool]:
    """All MCP tools the current caller may use, across enabled servers.

    When auth is OFF (local dev) there's no user, so current_roles() is empty; the rest of the
    app degrades OPEN in that case (has_role() returns True), so we mirror that here by treating
    the caller as Admin — otherwise the role filter would hide every tool locally. visible_tools
    itself stays pure (it just intersects role sets); the auth-off policy lives here.
    """
    roles = current_roles() if settings.auth_enabled else {"Admin"}
    tools = [_build_one(s, roles) for s in enabled_servers()]
    return [t for t in tools if t is not None]
