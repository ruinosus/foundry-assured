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

from app.agents.mcp.registry import (
    McpServer,
    enabled_servers,
    server_for_kind,
    visible_tools,
    visible_tools_for,
)
from app.core.auth import credential_for_request, current_roles
from app.core.settings import settings  # platform-global (auth_enabled)
from app.core.tenant import tenant_config  # per-tenant (mcp ado/github/azure)


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


def _foundry_connection_header_provider(connection_id: str):
    """Broker a non-OBO credential from the tenant's Foundry connection at call time — Foundry is
    the store; we never persist the secret. (Internal path; the hosted path uses get_mcp_tool.)"""
    def provider(_existing: dict) -> dict:
        from azure.ai.projects import AIProjectClient

        from app.core.auth import credential_for_request
        from app.core.tenant import tenant_config
        client = AIProjectClient(
            endpoint=tenant_config().foundry_project_endpoint, credential=credential_for_request())
        conn = client.connections.get(connection_id, include_credentials=True)
        key = conn.credentials.api_key
        return {"Authorization": f"Bearer {key}"}
    return provider


def _resolve_url(server: McpServer) -> str | None:
    """Fill any URL template from settings; None if the needed config is missing → skip."""
    cfg = tenant_config()
    if server.id == "azdo":
        org = cfg.mcp_ado_organization
        return server.url.format(org=org) if org else None
    if server.id == "azure":
        return cfg.mcp_azure_url or None  # registry url is empty; only if self-hosted
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
        pat = tenant_config().mcp_github_pat
        if not pat:
            return None  # no PAT configured → skip
        kwargs["header_provider"] = _static_header_provider(pat)
    else:
        return None  # oauth_passthrough (hosted) / unknown → skip on the internal path
    return MCPStreamableHTTPTool(**kwargs)


def _resolve_connection_url(server: McpServer, conn) -> str | None:
    """Shared-mode URL resolution — from the CONNECTION, not the flat mcp_* settings.

    Separate from self-hosted `_resolve_url` (do NOT merge): if the registry url is a {org}
    template, fill it from conn.endpoint (skip if empty); else use server.url as-is (e.g. a
    plain public url like learn). Fail-closed: missing endpoint for a templated url → None.
    """
    if "{org}" in server.url:
        return server.url.format(org=conn.endpoint) if conn.endpoint else None
    return server.url or None


def _build_from_connection(conn, roles: set[str]) -> MCPStreamableHTTPTool | None:
    if not conn.enabled:
        return None
    server = server_for_kind(conn.kind)
    if server is None:
        return None
    reads, writes = visible_tools_for(server, conn, roles)
    allowed = reads + writes
    if not allowed:
        return None

    url = _resolve_connection_url(server, conn)
    if not url:
        return None

    kwargs: dict = {
        "name": f"mcp_{server.id}",
        "url": url,
        "allowed_tools": allowed,
        "approval_mode": {
            "always_require_approval": list(writes),
            "never_require_approval": list(reads),
        },
    }
    if server.auth == "public":
        pass  # no auth header
    elif server.auth == "obo" and server.obo_scope:
        kwargs["header_provider"] = _obo_header_provider(server.obo_scope)
    elif conn.foundry_connection_id:
        # Non-OBO (github_pat / oauth_passthrough / other) carrying a foundry_connection_id →
        # broker the credential from the tenant's Foundry connection at call time (in memory,
        # never persisted). The closure is lazy: no Azure import/call until invoked.
        kwargs["header_provider"] = _foundry_connection_header_provider(conn.foundry_connection_id)
    else:
        # Non-OBO without any reference → needs the hosted/connection path; skip here.
        return None
    return MCPStreamableHTTPTool(**kwargs)


def build_from_connections(conns, roles: set[str]) -> list[MCPStreamableHTTPTool]:
    """Shared-mode build: tools from the tenant's Connections (not the flat registry path)."""
    tools = [_build_from_connection(c, roles) for c in conns]
    return [t for t in tools if t is not None]


def _current_tenant_connections():
    from app.core import auth as _auth
    from app.core.tenant import current_tenant_id
    store = _auth._tenant_store
    if store is None:
        return ()
    rec = store.get(current_tenant_id())
    return rec.connections if rec is not None else ()


def build_mcp_tools() -> list[MCPStreamableHTTPTool]:
    """All MCP tools the current caller may use.

    Mode-aware: in shared mode we build from the tenant's Connections; otherwise (self-hosted,
    the default) we keep EXACTLY today's registry path — iterate enabled_servers() and call the
    unchanged _build_one, reading the flat mcp_* fields via _resolve_url. Byte-identical.

    When auth is OFF (local dev) there's no user, so current_roles() is empty; the rest of the
    app degrades OPEN in that case (has_role() returns True), so we mirror that here by treating
    the caller as Admin — otherwise the role filter would hide every tool locally. visible_tools
    itself stays pure (it just intersects role sets); the auth-off policy lives here.
    """
    roles = current_roles() if settings.auth_enabled else {"Admin"}
    if settings.deployment_mode == "shared":
        return build_from_connections(_current_tenant_connections(), roles)
    else:                                   # literal else — any non-shared mode falls back to today
        tools = [_build_one(s, roles) for s in enabled_servers()]
        return [t for t in tools if t is not None]
