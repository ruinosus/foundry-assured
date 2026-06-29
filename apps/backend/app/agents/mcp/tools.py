"""Build live framework MCP tools from the registry for the CURRENT request.

Internal path only (MCPStreamableHTTPTool). Per server, filter tools to the caller's role
(registry.visible_tools), then construct the tool with:
  - allowed_tools = the visible read + write tool names (so the model can't call hidden ones)
  - approval_mode = "never_require" — native MCP approval does NOT execute over AG-UI
    (agent-framework #3199), so write approval is handled by OUR HITL card in the workflow,
    not here. We still gate WRITE visibility by role above; a Reader simply never sees a write.
  - the right auth per server:
      * public   → no header.
      * obo      → header_provider minting a per-user OBO bearer (lazy, at call time).
      * github_pat → header_provider with the shared GitHub PAT (GitHub's own OAuth, NOT
        Entra OBO — GitHub rejects Microsoft-audience tokens; see registry.py).

Servers whose required config is missing are SKIPPED (fail-closed): azdo needs an org,
github needs a PAT. The URL may be a template ({org}) resolved here from settings. Hosted
OAuth-passthrough is the hosted path (later chunk). Unknown auth → skipped.
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


def _static_header_provider(value: str):
    """A header_provider that injects a fixed Authorization bearer (e.g. a GitHub PAT)."""
    def provider(_existing: dict) -> dict:
        return {"Authorization": f"Bearer {value}"}
    return provider


def _resolve_url(server: McpServer) -> str | None:
    """Fill any URL template from settings; None if the needed config is missing → skip."""
    if server.id == "azdo":
        org = settings.mcp_ado_organization
        return server.url.format(org=org) if org else None
    if server.id == "azure":
        return settings.mcp_azure_url or None  # registry url is empty; only if self-hosted
    return server.url or None


def _build_one(server: McpServer, roles: set[str]) -> MCPStreamableHTTPTool | None:
    reads, writes = visible_tools(server, roles)
    allowed = reads + writes
    if not allowed:
        return None  # caller sees no tools on this server

    url = _resolve_url(server)
    if not url:
        return None  # required config missing (e.g. azdo org) → fail-closed

    kwargs: dict = {
        "name": f"mcp_{server.id}",
        "url": url,
        "allowed_tools": allowed,
        "approval_mode": "never_require",  # see module docstring (HITL handles writes)
    }
    if server.auth == "public":
        pass  # no auth header
    elif server.auth == "obo" and server.obo_scope:
        kwargs["header_provider"] = _obo_header_provider(server.obo_scope)
    elif server.auth == "github_pat":
        if not settings.mcp_github_pat:
            return None  # no PAT configured → skip
        kwargs["header_provider"] = _static_header_provider(settings.mcp_github_pat)
    else:
        return None  # oauth_passthrough (hosted) / unknown → skip on the internal path
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
