"""MCP servers as data — the single source for both the internal (MCPStreamableHTTPTool)
and hosted (get_mcp_tool/toolbox) paths. PURE: no network, no framework, no auth imports,
so it's unit-testable in isolation (eval/mcp_registry_test.py).

Governance lives here as data, not code branches: each server declares which tools are
reads vs writes and the minimum role for each. A tool that is on NEITHER list is treated
as a WRITE (fail-closed) — an unclassified new tool can't slip through as an open read.

Role model (flat, not a ladder — see app/core/auth.py APP_ROLES): "read" access is granted
to Reader/Author/Approver/Admin; "write" access only to Author/Admin. min_role/min_role_write
name which grant a server's tools require.
"""

from __future__ import annotations

from dataclasses import dataclass

# Which concrete roles satisfy a named grant. has_role(*roles) checks ANY membership.
READ_ROLES = ("Reader", "Author", "Approver", "Admin")
WRITE_ROLES = ("Author", "Admin")
_GRANTS = {"Reader": READ_ROLES, "Author": WRITE_ROLES}


@dataclass(frozen=True)
class McpServer:
    id: str                              # learn · azure · entra · azdo · github · m365
    label: str
    url: str                             # remote MCP endpoint
    auth: str                            # "public" | "obo" | "github_pat" | "oauth_passthrough"
    obo_scope: str | None = None         # downstream scope for OBO (internal path)
    read_tools: tuple[str, ...] = ()     # → never_require approval
    write_tools: tuple[str, ...] = ()    # → always_require (routed via our HITL on AG-UI)
    min_role: str = "Reader"             # grant required to see read tools
    min_role_write: str = "Author"       # grant required to see write tools
    enabled: bool = True


# NOTE on tool names: read_tools/write_tools are HAND-CURATED (governance decision, not
# server-trusted). The names below are the documented tool names per server; verify against
# each server's live tool list when wiring that server (the unclassified→write fail-closed
# default protects us if a name drifts). Learn's are confirmed (microsoft_docs_*).
SERVERS: tuple[McpServer, ...] = (
    McpServer(
        id="learn",
        label="Microsoft Learn",
        url="https://learn.microsoft.com/api/mcp",
        auth="public",
        read_tools=("microsoft_docs_search", "microsoft_docs_fetch"),
    ),
    # Azure MCP has NO Microsoft-managed remote endpoint — it ships as a LOCAL stdio server
    # (`npx @azure/mcp`) or must be self-hosted on Azure Container Apps to get an HTTPS URL.
    # So it does NOT fit the MCPStreamableHTTPTool remote+OBO model out of the box: disabled
    # until self-hosted (then set mcp_azure_url) or wired via MCPStdioTool with ambient creds.
    # Verified: github.com/mcp/com.microsoft/azure.
    McpServer(
        id="azure",
        label="Azure",
        url="",  # self-host on Container Apps → set via settings.mcp_azure_url; else stdio (local)
        auth="obo",
        obo_scope="https://management.azure.com/.default",
        read_tools=("azure_resource_list", "azure_cost_query", "azure_diagnostics"),
        write_tools=("azure_resource_deploy",),
        enabled=False,  # no managed remote endpoint — see comment
    ),
    # No confirmed FIRST-PARTY hosted-remote Entra MCP endpoint; the Entra identity surface in
    # Foundry is via the Graph / Agent 365 MCP servers (Frontier-tenant gated). Disabled until a
    # real remote endpoint exists (then set the url). Verified: Foundry MCP-auth + Agent 365 docs.
    McpServer(
        id="entra",
        label="Microsoft Entra",
        url="",  # no first-party remote endpoint yet
        auth="obo",
        obo_scope="https://graph.microsoft.com/.default",
        read_tools=("entra_directory_query",),
        write_tools=("entra_directory_change",),
        enabled=False,  # no remote endpoint — see comment
    ),
    # Azure DevOps Remote MCP Server (public preview) — REAL hosted endpoint, streamable HTTP,
    # Entra auth (so OBO works). URL is per-organization; {org} is filled from settings at build
    # time. Verified: learn.microsoft.com/azure/devops/mcp-server/remote-mcp-server.
    McpServer(
        id="azdo",
        label="Azure DevOps",
        url="https://mcp.dev.azure.com/{org}",  # {org} → settings.mcp_ado_organization
        auth="obo",
        obo_scope="499b84ac-1321-427f-aa17-267ca6975798/.default",  # Azure DevOps resource (stable)
        read_tools=("azdo_workitem_query", "azdo_pipeline_list"),
        write_tools=("azdo_workitem_create",),
        # enabled (real endpoint); the builder skips it until settings.mcp_ado_organization is set.
    ),
    # GitHub auth is NOT Entra OBO. GitHub's MCP advertises
    # authorization_servers=["https://github.com/login/oauth"] — it validates GitHub-issued
    # tokens only. An Entra OBO token has a Microsoft audience, which GitHub rejects; Foundry
    # also blocks it ("Cannot pass Microsoft token to untrusted MCP endpoint"). Per-user
    # identity still works, but via GitHub's own OAuth: a PAT/OAuth bearer here (internal),
    # or custom-OAuth identity passthrough (hosted). Verified against learn.microsoft.com
    # /azure/foundry/agents/how-to/mcp-authentication.
    McpServer(
        id="github",
        label="GitHub",
        url="https://api.githubcopilot.com/mcp/",
        auth="github_pat",
        read_tools=("github_repo_search", "github_issue_list"),
        write_tools=("github_issue_create",),
    ),
    McpServer(
        id="m365",
        label="Microsoft 365",
        url="https://<m365-mcp-endpoint>",  # TODO: confirm when wiring
        auth="oauth_passthrough",
        obo_scope="https://graph.microsoft.com/.default",
        read_tools=(),
        write_tools=(),
        enabled=False,  # no M365 in this tenant — see spec open question #1
    ),
)


def get_server(server_id: str) -> McpServer:
    for s in SERVERS:
        if s.id == server_id:
            return s
    raise KeyError(server_id)


def enabled_servers() -> tuple[McpServer, ...]:
    return tuple(s for s in SERVERS if s.enabled)


def classify_tool(server: McpServer, tool_name: str) -> str:
    """'read' | 'write'. Fail-closed: anything not explicitly a read is a write."""
    if tool_name in server.read_tools:
        return "read"
    return "write"


def _granted(roles: set[str], min_role: str) -> bool:
    """True if `roles` satisfies the named grant (READ_ROLES / WRITE_ROLES)."""
    return bool(set(_GRANTS[min_role]) & roles)


def visible_tools(server: McpServer, roles: set[str]) -> tuple[list[str], list[str]]:
    """(read_tools, write_tools) this caller may see, by role. The caller never sees a tool
    above their grant — and a no-role caller sees nothing (fail-closed)."""
    reads = list(server.read_tools) if _granted(roles, server.min_role) else []
    writes = list(server.write_tools) if _granted(roles, server.min_role_write) else []
    return reads, writes
