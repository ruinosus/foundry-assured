"""Decisão de conformidade entre um binding inerte e metadata MCP revisada."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.modules.foundry.public import (
    resolve_toolbox_default_version,
    resolve_toolbox_version,
)
from app.modules.okf.public import McpBinding, parse_mcp_binding
from app.modules.platform_ops.internal.mcp_classification import (
    ClassificationNotFound,
    derive_snapshot_runtime,
)
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


def _snapshot_reasons(
    binding: McpBinding, source: dict[str, Any], snapshot: dict[str, Any]
) -> list[str]:
    observed = snapshot.get("source") or {}
    source_changed = (
        observed.get("kind") != source.get("kind")
        or observed.get("id") != source.get("id")
        or str(observed.get("resolvedVersion") or "")
        != str(source.get("resolvedVersion") or "")
    )
    reasons = (
        ["MCP_SNAPSHOT_STALE"]
        if source_changed or snapshot.get("status") == "stale"
        else []
    )
    if snapshot.get("hash") != binding.snapshot_hash and not reasons:
        reasons.append("MCP_SNAPSHOT_STALE")
    if binding.use_default:
        reasons.append("MCP_DEFAULT_VERSION_REQUIRES_PIN")
    if (snapshot.get("drift") or {}).get("blocking"):
        reasons.append("MCP_DRIFT_BLOCKING")
    return reasons


def _selected_tools(
    binding: McpBinding,
    snapshot: dict[str, Any],
    runtime: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str]]:
    available = {
        item.get("name")
        for item in snapshot.get("tools", ())
        if isinstance(item, dict)
    }
    missing = [name for name in binding.tools if name not in available]
    states = {item["name"]: item for item in runtime["tools"]}
    selected = []
    for name in binding.tools:
        effect = (
            "quarantined"
            if name in missing
            else states.get(name, {}).get("effect", "quarantined")
        )
        selected.append(
            {
                "name": name,
                "status": "pass"
                if effect in {"read", "write_requires_approval"}
                else "block",
                "effectiveEffect": effect,
            }
        )
    return selected, missing


def _append_tool_reasons(
    reasons: list[str], selected: list[dict[str, Any]], missing: list[str]
) -> None:
    effects = {item["effectiveEffect"] for item in selected}
    if missing:
        reasons.append("MCP_TOOL_NOT_FOUND")
    elif "quarantined" in effects and "MCP_SNAPSHOT_STALE" not in reasons:
        reasons.append("MCP_TOOL_QUARANTINED")
    if "forbidden" in effects:
        reasons.append("MCP_TOOL_FORBIDDEN")


def evaluate_mcp_binding(
    spec: dict[str, Any],
    *,
    toolbox_resolver=resolve_toolbox_version,
    toolbox_default_resolver=resolve_toolbox_default_version,
    snapshot_reader=get_snapshot,
    endpoint_resolver=resolve_approved_endpoint,
    runtime_resolver=derive_snapshot_runtime,
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

    reasons = _snapshot_reasons(binding, source, snapshot)

    try:
        runtime = runtime_resolver(
            binding.snapshot_id,
            list(binding.tools),
            current="MCP_SNAPSHOT_STALE" not in reasons,
        )
    except ClassificationNotFound as exc:
        raise ConformityNotFound("MCP_SOURCE_NOT_FOUND") from exc
    selected_tools, missing_tools = _selected_tools(binding, snapshot, runtime)
    _append_tool_reasons(reasons, selected_tools, missing_tools)

    return {
        "status": "block" if reasons else "pass",
        "reasons": reasons,
        "source": source,
        "snapshot": {"id": binding.snapshot_id, "hash": binding.snapshot_hash},
        "tools": selected_tools,
        "runtime": {
            "allowedTools": [
                item["name"] for item in selected_tools if item["status"] == "pass"
            ],
            "approvalMode": runtime["approvalMode"],
        },
    }
