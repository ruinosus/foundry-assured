"""Discovery administrativa de metadata MCP, sem qualquer caminho de execução de tool."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import rfc8785

from app.modules.audit.public import read_evidence, record, write_evidence
from app.modules.foundry.public import resolve_toolbox_version
from app.modules.tenancy.public import current_tenant_id

_ANNOTATIONS = ("title", "readOnlyHint", "destructiveHint", "idempotentHint", "openWorldHint")
_MAX_TOOLS = 200
_MAX_SCHEMA_BYTES = 32 * 1024
_MAX_SCHEMA_DEPTH = 12
_MAX_SCHEMA_PROPERTIES = 200
_MAX_SNAPSHOT_BYTES = 256 * 1024
_PROJECTIONS: dict[tuple[str, str], dict] = {}


class DiscoveryRejected(ValueError):
    """A origem ou metadata MCP não satisfaz o contrato de discovery."""


class _CapturingSession:
    """Proxy transparente que observa tools/list sem mudar a paginação do framework."""

    def __init__(self, session: Any) -> None:
        self._session = session
        self.tools: list[Any] = []

    def __getattr__(self, name: str) -> Any:
        return getattr(self._session, name)

    async def list_tools(self, *args, **kwargs):
        result = await self._session.list_tools(*args, **kwargs)
        self.tools.extend(result.tools)
        return result


def _tenant_key() -> str:
    return current_tenant_id() or "self-hosted"


def _plain(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _plain(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_plain(item) for item in value]
    if hasattr(value, "model_dump"):
        return _plain(value.model_dump(by_alias=True, exclude_none=True))
    raise DiscoveryRejected("Metadata MCP contém tipo não suportado.")


def _schema_property_count(node: Any, depth: int = 1) -> int:
    if depth > _MAX_SCHEMA_DEPTH:
        raise DiscoveryRejected("Schema MCP excede a profundidade permitida.")
    if isinstance(node, list):
        return sum(_schema_property_count(child, depth + 1) for child in node)
    if not isinstance(node, dict):
        return 0
    properties = node.get("properties")
    own_count = len(properties) if isinstance(properties, dict) else 0
    total = own_count + sum(
        _schema_property_count(child, depth + 1) for child in node.values()
    )
    if total > _MAX_SCHEMA_PROPERTIES:
        raise DiscoveryRejected("Schema MCP excede o limite de propriedades.")
    return total


def _schema(value: Any) -> dict | None:
    if value is None:
        return None
    schema = _plain(value)
    if not isinstance(schema, dict):
        raise DiscoveryRejected("Schema MCP deve ser um objeto JSON.")
    _schema_property_count(schema)
    if len(rfc8785.dumps(schema)) > _MAX_SCHEMA_BYTES:
        raise DiscoveryRejected("Schema MCP excede o limite permitido.")
    return schema


def _annotations(value: Any) -> dict:
    raw = _plain(value) if value else {}
    if not isinstance(raw, dict):
        return {}
    return {key: raw[key] for key in _ANNOTATIONS if key in raw}


def _hash(value: dict) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _field(tool: Any, name: str, default: Any = None) -> Any:
    if isinstance(tool, dict):
        return tool.get(name, default)
    return getattr(tool, name, default)


def _sanitize(tool: Any) -> dict:
    name = str(_field(tool, "name", "") or "")
    description = str(_field(tool, "description", "") or "")
    if not name or len(name) > 128:
        raise DiscoveryRejected("Nome de tool MCP inválido.")
    if len(description) > 2048:
        raise DiscoveryRejected("Descrição de tool MCP excede o limite permitido.")
    contract = {
        "name": name,
        "description": description,
        "inputSchema": _schema(_field(tool, "inputSchema")) or {},
        "outputSchema": _schema(_field(tool, "outputSchema")),
        "annotations": _annotations(_field(tool, "annotations")),
    }
    return {**contract, "contractHash": _hash(contract)}


def canonical_tool_hash(tool: Any) -> str:
    """Calcula SHA-256/JCS somente sobre o contrato MCP permitido."""
    return str(_sanitize(tool)["contractHash"])


def _protocol_version(tool: Any) -> str:
    explicit = getattr(tool, "protocol_version", None)
    session = getattr(tool, "session", None)
    return str(explicit or getattr(session, "_protocol_version", "") or "unknown")


def _default_mcp_factory(**kwargs):
    from agent_framework import MCPStreamableHTTPTool

    return MCPStreamableHTTPTool(**kwargs)


def _auth_header_provider(_headers: dict[str, Any]) -> dict[str, str]:
    from app.shared.auth import credential_for_request

    token = credential_for_request().get_token("https://ai.azure.com/.default").token
    return {"Authorization": f"Bearer {token}"}


async def discover_toolbox(
    name: str,
    version: str,
    *,
    toolbox_resolver=resolve_toolbox_version,
    mcp_factory=_default_mcp_factory,
    evidence_store=None,
    source_store=None,
    audit_recorder=record,
    http_client_factory=None,
) -> dict:
    """Executa initialize + tools/list e grava somente o snapshot sanitizado."""
    source = toolbox_resolver(name, version)
    normalized_source = {
        "kind": "toolbox",
        "id": source["id"],
        "name": source["name"],
        "resolvedVersion": source["version"],
        "url": source["url"],
    }
    try:
        return await _discover_source(
            normalized_source,
            header_provider=_auth_header_provider,
            follow_redirects=False,
            mcp_factory=mcp_factory,
            evidence_store=evidence_store,
            source_store=source_store,
            audit_recorder=audit_recorder,
            http_client_factory=http_client_factory,
        )
    except Exception as exc:
        _mark_failed_discovery(normalized_source, exc, source_store)
        raise


async def discover_endpoint_source(
    source: dict[str, Any],
    *,
    follow_redirects: bool,
    header_provider,
    evidence_store=None,
    source_store=None,
    audit_recorder=record,
    mcp_factory=_default_mcp_factory,
    http_client_factory=None,
) -> dict:
    """Descobre uma origem direta já aprovada e validada pela política de egress."""
    if follow_redirects:
        raise DiscoveryRejected("Redirect MCP não é permitido.")
    try:
        return await _discover_source(
            source,
            header_provider=header_provider,
            follow_redirects=False,
            mcp_factory=mcp_factory,
            evidence_store=evidence_store,
            source_store=source_store,
            audit_recorder=audit_recorder,
            http_client_factory=http_client_factory,
        )
    except Exception as exc:
        _mark_failed_discovery(source, exc, source_store)
        raise


def _mark_failed_discovery(source: dict[str, Any], exc: Exception, source_store) -> None:
    from app.modules.platform_ops.internal.mcp_drift import mark_mcp_source_stale

    error_code = "MCP_SOURCE_UNAVAILABLE"
    if isinstance(exc, TimeoutError):
        error_code = "MCP_DISCOVERY_TIMEOUT"
    elif isinstance(exc, DiscoveryRejected):
        error_code = "MCP_PROTOCOL_INVALID"
    mark_mcp_source_stale(source, error_code=error_code, store=source_store)


async def _discover_source(
    source: dict[str, Any],
    *,
    header_provider,
    follow_redirects: bool,
    mcp_factory,
    evidence_store,
    source_store,
    audit_recorder,
    http_client_factory,
) -> dict:
    tenant_key = _tenant_key()
    snapshot_id = f"msnap_{uuid4().hex}"

    async with AsyncExitStack() as stack:
        http_client = None
        if http_client_factory is None and mcp_factory is _default_mcp_factory:
            import httpx

            http_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    timeout=httpx.Timeout(10, connect=5),
                    follow_redirects=follow_redirects,
                )
            )
        elif http_client_factory is not None:
            http_client = await stack.enter_async_context(http_client_factory())

        kwargs = {
            "name": f"discovery-{source['id']}",
            "url": source["url"],
            "load_tools": False,
            "load_prompts": False,
            "request_timeout": 10,
            "header_provider": header_provider,
        }
        if http_client is not None:
            kwargs["http_client"] = http_client

        async with asyncio.timeout(15):
            tool = await stack.enter_async_context(mcp_factory(**kwargs))
            if getattr(tool, "session", None) is None:
                raise DiscoveryRejected("Sessão MCP não foi inicializada.")
            captured = _CapturingSession(tool.session)
            tool.session = captured
            await tool.load_tools()

        raw_tools = captured.tools
        if len(raw_tools) > _MAX_TOOLS:
            raise DiscoveryRejected("Servidor MCP excede o limite de tools.")
        tools = sorted((_sanitize(item) for item in raw_tools), key=lambda item: item["name"])
        if len({item["name"] for item in tools}) != len(tools):
            raise DiscoveryRejected("Servidor MCP devolveu nomes de tool duplicados.")

        observed_at = datetime.now(UTC).isoformat(timespec="seconds")
        snapshot = {
            "snapshotId": snapshot_id,
            "tenantKey": tenant_key,
            "source": {
                "kind": source["kind"],
                "id": source["id"],
                **({"name": source["name"]} if source.get("name") else {}),
                **(
                    {"resolvedVersion": source["resolvedVersion"]}
                    if source.get("resolvedVersion") is not None
                    else {}
                ),
            },
            "observedAt": observed_at,
            "protocolVersion": _protocol_version(tool),
            "tools": tools,
        }
        snapshot["snapshotHash"] = _hash(
            {
                "source": snapshot["source"],
                "protocolVersion": snapshot["protocolVersion"],
                "tools": tools,
            }
        )
        if len(rfc8785.dumps(snapshot)) > _MAX_SNAPSHOT_BYTES:
            raise DiscoveryRejected("Snapshot MCP excede o limite permitido.")
        write_evidence(snapshot_id, snapshot, scope=tenant_key, store=evidence_store)

    projection = {
        "snapshotId": snapshot_id,
        "source": snapshot["source"],
        "resolvedVersion": source.get("resolvedVersion"),
        "observedAt": snapshot["observedAt"],
        "protocolVersion": snapshot["protocolVersion"],
        "status": "current",
        "hash": snapshot["snapshotHash"],
        "tools": [
            {"name": item["name"], "description": item["description"], "hash": item["contractHash"]}
            for item in tools
        ],
        "drift": None,
    }
    from app.modules.platform_ops.internal.mcp_drift import observe_mcp_snapshot

    state = observe_mcp_snapshot(
        snapshot,
        store=source_store,
        snapshot_reader=lambda identifier: read_evidence(
            identifier, scope=tenant_key, store=evidence_store
        ),
    )
    projection["status"] = state["status"]
    projection["drift"] = state["drift"]
    audit_recorder(
        scope=tenant_key,
        actor="system:mcp-discovery",
        kind="write",
        summary="Snapshot MCP observado",
        ref=snapshot_id,
        detail={
            "sourceId": snapshot["source"]["id"],
            "snapshotHash": snapshot["snapshotHash"],
            "toolCount": len(tools),
            "driftCount": len((state.get("drift") or {}).get("tools", ())),
        },
    )
    _PROJECTIONS[(tenant_key, snapshot_id)] = projection
    return projection


def get_snapshot(snapshot_id: str, *, evidence_store=None) -> dict | None:
    projection = _PROJECTIONS.get((_tenant_key(), snapshot_id))
    if projection is None:
        return None
    snapshot = read_evidence(snapshot_id, scope=_tenant_key(), store=evidence_store)
    if snapshot is None or snapshot.get("tenantKey") != _tenant_key():
        return None
    from app.modules.platform_ops.internal.mcp_drift import get_mcp_source

    state = get_mcp_source(str((projection.get("source") or {}).get("id") or ""))
    if state is None:
        return projection
    return {**projection, "status": state["status"], "drift": state["drift"]}
