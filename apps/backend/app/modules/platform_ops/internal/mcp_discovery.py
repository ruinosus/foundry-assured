"""Discovery administrativa de metadata MCP, sem qualquer caminho de execução de tool."""

from __future__ import annotations

import asyncio
import hashlib
from contextlib import AsyncExitStack
from datetime import UTC, datetime
from typing import Any
from uuid import uuid4

import rfc8785

from app.modules.audit.public import read_evidence, write_evidence
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


def _schema(value: Any) -> dict | None:
    if value is None:
        return None
    schema = _plain(value)
    if not isinstance(schema, dict):
        raise DiscoveryRejected("Schema MCP deve ser um objeto JSON.")
    property_count = 0

    def visit(node: Any, depth: int) -> None:
        nonlocal property_count
        if depth > _MAX_SCHEMA_DEPTH:
            raise DiscoveryRejected("Schema MCP excede a profundidade permitida.")
        if isinstance(node, dict):
            properties = node.get("properties")
            if isinstance(properties, dict):
                property_count += len(properties)
                if property_count > _MAX_SCHEMA_PROPERTIES:
                    raise DiscoveryRejected("Schema MCP excede o limite de propriedades.")
            for child in node.values():
                visit(child, depth + 1)
        elif isinstance(node, list):
            for child in node:
                visit(child, depth + 1)

    visit(schema, 1)
    if len(rfc8785.dumps(schema)) > _MAX_SCHEMA_BYTES:
        raise DiscoveryRejected("Schema MCP excede o limite permitido.")
    return schema


def _annotations(tool: Any) -> dict:
    raw = _plain(getattr(tool, "annotations", None)) if getattr(tool, "annotations", None) else {}
    if not isinstance(raw, dict):
        return {}
    return {key: raw[key] for key in _ANNOTATIONS if key in raw}


def _hash(value: dict) -> str:
    return hashlib.sha256(rfc8785.dumps(value)).hexdigest()


def _sanitize(tool: Any) -> dict:
    name = str(getattr(tool, "name", "") or "")
    description = str(getattr(tool, "description", "") or "")
    if not name or len(name) > 128:
        raise DiscoveryRejected("Nome de tool MCP inválido.")
    if len(description) > 2048:
        raise DiscoveryRejected("Descrição de tool MCP excede o limite permitido.")
    contract = {
        "name": name,
        "description": description,
        "inputSchema": _schema(getattr(tool, "inputSchema", None)) or {},
        "outputSchema": _schema(getattr(tool, "outputSchema", None)),
        "annotations": _annotations(tool),
    }
    return {**contract, "contractHash": _hash(contract)}


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
    http_client_factory=None,
) -> dict:
    """Executa initialize + tools/list e grava somente o snapshot sanitizado."""
    source = toolbox_resolver(name, version)
    tenant_key = _tenant_key()
    snapshot_id = f"msnap_{uuid4().hex}"

    async with AsyncExitStack() as stack:
        http_client = None
        if http_client_factory is None and mcp_factory is _default_mcp_factory:
            import httpx

            http_client = await stack.enter_async_context(
                httpx.AsyncClient(
                    timeout=httpx.Timeout(10, connect=5),
                    follow_redirects=False,
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
            "header_provider": _auth_header_provider,
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
                "kind": "toolbox",
                "id": source["id"],
                "name": source["name"],
                "resolvedVersion": source["version"],
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
        "resolvedVersion": source["version"],
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
    _PROJECTIONS[(tenant_key, snapshot_id)] = projection
    return projection


def get_snapshot(snapshot_id: str, *, evidence_store=None) -> dict | None:
    projection = _PROJECTIONS.get((_tenant_key(), snapshot_id))
    if projection is None:
        return None
    snapshot = read_evidence(snapshot_id, scope=_tenant_key(), store=evidence_store)
    if snapshot is None or snapshot.get("tenantKey") != _tenant_key():
        return None
    return projection
