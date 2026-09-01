"""Tool-driven ops concierge over the Microsoft first-party MCP servers.

`SERVERS` is the catalog, and it is DATA of this domain. `tenancy` used to import it directly
to validate connection kinds — that was the core↔agents cycle. The composition root now hands
the ids to tenancy instead (ADR-017).

Write tools sit behind the framework's native tool approval; per-tool role gates
(min_role/min_role_write) still live in `internal/mcp_registry.py` as Python. Moving them into
the AgentSchema documents is Phase 3.5's job (ADR-018).
"""

from app.modules.platform_ops.internal.mcp_classification import (
    ClassificationConflict,
    ClassificationInvalid,
    ClassificationNotFound,
    InMemoryClassificationStore,
    TableClassificationStore,
    classify_mcp_tool,
    derive_runtime_config,
    derive_snapshot_runtime,
    effective_tool_state,
    project_snapshot_classifications,
)
from app.modules.platform_ops.internal.mcp_conformity import (
    ConformityNotFound,
    evaluate_mcp_binding,
)
from app.modules.platform_ops.internal.mcp_discovery import (
    DiscoveryLimitExceeded,
    DiscoveryRejected,
    canonical_tool_hash,
    discover_toolbox,
    get_snapshot,
)
from app.modules.platform_ops.internal.mcp_drift import (
    InMemoryMcpSourceStore,
    SnapshotReviewConflict,
    SnapshotReviewInvalid,
    SnapshotReviewNotFound,
    TableMcpSourceStore,
    compare_mcp_snapshots,
    get_mcp_source,
    mark_mcp_source_stale,
    observe_mcp_snapshot,
    review_mcp_snapshot,
    source_tool_is_current,
)
from app.modules.platform_ops.internal.mcp_egress import (
    DiscoveryBusy,
    EgressDenied,
    InMemoryDiscoveryLeaseStore,
    TableDiscoveryLeaseStore,
    discover_endpoint,
    validate_mcp_origin,
)
from app.modules.platform_ops.internal.mcp_endpoints import (
    EndpointConflict,
    EndpointInvalid,
    InMemoryEndpointStore,
    approve_mcp_endpoint,
    create_mcp_endpoint,
    get_mcp_endpoint,
    list_mcp_endpoints,
    resolve_approved_endpoint,
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
from app.modules.platform_ops.internal.registry_bindings import (
    InMemoryRegistryBindingStore,
    RegistryBindingConflict,
    RegistryBindingInvalid,
    RegistryBindingScope,
    RegistryBindingService,
    TableRegistryBindingStore,
    registry_binding_store,
)

__all__ = [
    "SERVERS",
    "ClassificationConflict",
    "ClassificationInvalid",
    "ClassificationNotFound",
    "ConformityNotFound",
    "DiscoveryBusy",
    "DiscoveryLimitExceeded",
    "DiscoveryRejected",
    "EgressDenied",
    "EndpointConflict",
    "EndpointInvalid",
    "InMemoryClassificationStore",
    "InMemoryDiscoveryLeaseStore",
    "InMemoryEndpointStore",
    "InMemoryMcpSourceStore",
    "InMemoryRegistryBindingStore",
    "RegistryBindingConflict",
    "RegistryBindingInvalid",
    "RegistryBindingScope",
    "RegistryBindingService",
    "SnapshotReviewConflict",
    "SnapshotReviewInvalid",
    "SnapshotReviewNotFound",
    "TableClassificationStore",
    "TableDiscoveryLeaseStore",
    "TableMcpSourceStore",
    "TableRegistryBindingStore",
    "approve_mcp_endpoint",
    "build_from_connections",
    "build_hosted_from_connections",
    "build_mcp_tools",
    "build_platform_agent",
    "canonical_tool_hash",
    "classify_mcp_tool",
    "compare_mcp_snapshots",
    "create_mcp_endpoint",
    "derive_runtime_config",
    "derive_snapshot_runtime",
    "discover_endpoint",
    "discover_toolbox",
    "effective_tool_state",
    "evaluate_mcp_binding",
    "get_mcp_endpoint",
    "get_mcp_source",
    "get_server",
    "get_snapshot",
    "list_mcp_endpoints",
    "mark_mcp_source_stale",
    "observe_mcp_snapshot",
    "platform_agent_proxy",
    "platform_configured",
    "project_snapshot_classifications",
    "registry_binding_store",
    "resolve_approved_endpoint",
    "review_mcp_snapshot",
    "server_for_kind",
    "source_tool_is_current",
    "validate_mcp_origin",
    "visible_tools_for",
]
