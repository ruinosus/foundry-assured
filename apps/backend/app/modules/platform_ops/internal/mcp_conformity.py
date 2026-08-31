"""Decisão de conformidade entre um binding inerte e metadata MCP revisada."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.modules.foundry.public import (
    resolve_toolbox_default_version,
    resolve_toolbox_version,
)
from app.modules.okf.public import McpBinding, parse_mcp_binding
from app.modules.platform_ops.internal.mcp_discovery import get_snapshot
from app.modules.platform_ops.internal.mcp_endpoints import resolve_approved_endpoint


class ConformityNotFound(LookupError):
    """Uma referência não existe no escopo do tenant atual."""


def _toolbox_source(source: dict[str, Any]) -> dict[str, Any]:
    return {
        "kind": "toolbox",
        "id": source["id"],
        "name": source["name"],
        "resolvedVersion": str(source["version"]),
    }


def _resolve_source(
    binding: McpBinding,
    *,
    toolbox_resolver: Callable[[str, str], dict[str, Any]],
    toolbox_default_resolver: Callable[[str], dict[str, Any]],
    endpoint_resolver: Callable[[str], dict[str, Any] | None] | None,
) -> dict[str, Any]:
    if binding.source_kind == "endpoint":
        source = endpoint_resolver(binding.source_id) if endpoint_resolver else None
        if source is None:
            raise ConformityNotFound("MCP_SOURCE_NOT_FOUND")
        return source
    if binding.source_name is None:
        raise ConformityNotFound("MCP_SOURCE_NOT_FOUND")
    source = (
        toolbox_default_resolver(binding.source_name)
        if binding.use_default
        else toolbox_resolver(binding.source_name, binding.source_version or "")
    )
    return _toolbox_source(source)


def evaluate_mcp_binding(
    spec: dict[str, Any],
    *,
    toolbox_resolver=resolve_toolbox_version,
    toolbox_default_resolver=resolve_toolbox_default_version,
    snapshot_reader=get_snapshot,
    endpoint_resolver=resolve_approved_endpoint,
) -> dict[str, Any]:
    """Valida referências no tenant atual e devolve uma decisão estável, sem persistir."""
    binding = parse_mcp_binding(spec)
    source = _resolve_source(
        binding,
        toolbox_resolver=toolbox_resolver,
        toolbox_default_resolver=toolbox_default_resolver,
        endpoint_resolver=endpoint_resolver,
    )
    snapshot = snapshot_reader(binding.snapshot_id)
    if snapshot is None:
        raise ConformityNotFound("MCP_SOURCE_NOT_FOUND")

    reasons: list[str] = []
    observed_source = snapshot.get("source") or {}
    if (
        observed_source.get("kind") != source.get("kind")
        or observed_source.get("id") != source.get("id")
        or str(observed_source.get("resolvedVersion") or "")
        != str(source.get("resolvedVersion") or "")
    ):
        reasons.append("MCP_SNAPSHOT_STALE")
    if snapshot.get("hash") != binding.snapshot_hash and "MCP_SNAPSHOT_STALE" not in reasons:
        reasons.append("MCP_SNAPSHOT_STALE")

    available_tools = {
        item.get("name") for item in snapshot.get("tools", ()) if isinstance(item, dict)
    }
    selected_tools = [
        {"name": name, "status": "pass" if name in available_tools else "block"}
        for name in binding.tools
    ]
    if any(item["status"] == "block" for item in selected_tools):
        reasons.append("MCP_TOOL_NOT_FOUND")
    if binding.use_default:
        reasons.append("MCP_DEFAULT_VERSION_REQUIRES_PIN")

    return {
        "status": "block" if reasons else "pass",
        "reasons": reasons,
        "source": source,
        "snapshot": {"id": binding.snapshot_id, "hash": binding.snapshot_hash},
        "tools": selected_tools,
    }
