"""Tool-driven ops concierge over the Microsoft first-party MCP servers.

`SERVERS` is the catalog, and it is DATA of this domain. `tenancy` used to import it directly
to validate connection kinds — that was the core↔agents cycle. The composition root now hands
the ids to tenancy instead (ADR-017).

Write tools sit behind the framework's native tool approval; per-tool role gates
(min_role/min_role_write) still live in `internal/mcp_registry.py` as Python. Moving them into
the AgentSchema documents is Phase 3.5's job (ADR-018).
"""

from app.modules.platform_ops.internal.mcp_conformity import (
    ConformityNotFound,
    evaluate_mcp_binding,
)
from app.modules.platform_ops.internal.mcp_discovery import (
    DiscoveryRejected,
    discover_toolbox,
    get_snapshot,
)
from app.modules.platform_ops.internal.mcp_registry import (
    SERVERS,
    get_server,
    server_for_kind,
    visible_tools_for,
)
from app.modules.platform_ops.internal.mcp_tools import (
    build_from_connections,
    build_hosted_from_connections,
    build_mcp_tools,
)
from app.modules.platform_ops.internal.platform import (
    build_platform_agent,
    platform_agent_proxy,
    platform_configured,
)

__all__ = [
    "SERVERS",
    "ConformityNotFound",
    "DiscoveryRejected",
    "build_from_connections",
    "build_hosted_from_connections",
    "build_mcp_tools",
    "build_platform_agent",
    "discover_toolbox",
    "evaluate_mcp_binding",
    "get_server",
    "get_snapshot",
    "platform_agent_proxy",
    "platform_configured",
    "server_for_kind",
    "visible_tools_for",
]
