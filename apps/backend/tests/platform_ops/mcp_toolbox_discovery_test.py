"""F01: projeção e discovery de Toolbox sem executar tools."""

from __future__ import annotations

import asyncio
import hashlib
import json
import sys
from dataclasses import dataclass
from types import SimpleNamespace
from typing import ClassVar

import rfc8785

from app.modules.audit.public import (
    EvidenceExists,
    InMemoryEvidenceStore,
    read_evidence,
    write_evidence,
)
from app.modules.foundry.public import list_toolbox_projection
from app.modules.platform_ops.public import (
    DiscoveryRejected,
    discover_toolbox,
    get_snapshot,
)
from app.modules.tenancy.public import current_tenant_id, set_current_tenant


@dataclass
class _Version:
    version: str
    created_at: str
    description: str = ""


@dataclass
class _Default:
    version: str


@dataclass
class _Toolbox:
    name: str
    id: str
    default_version: _Default


class _Pages:
    continuation_token = "next-page"

    def __iter__(self):
        yield [_Toolbox("tenant-tools", "tb-1", _Default("2"))]


class _Listing:
    def by_page(self, continuation_token=None):
        assert continuation_token == "page-1"
        return _Pages()


class _Toolboxes:
    def list(self, *, limit):
        assert limit == 25
        return _Listing()

    def list_versions(self, name):
        assert name == "tenant-tools"
        return [
            _Version("1", "2026-08-30T10:00:00+00:00", "anterior"),
            _Version("2", "2026-08-31T10:00:00+00:00", "atual"),
        ]

    def get(self, name):
        assert name == "tenant-tools"
        return _Toolbox("tenant-tools", "tb-1", _Default("2"))


class _Client:
    endpoint = "https://example.services.ai.azure.com/api/projects/tenant"
    toolboxes = _Toolboxes()
    closed = False

    def close(self):
        self.closed = True


class _Function:
    input_schema: ClassVar = {
        "type": "object",
        "properties": {"query": {"type": "string"}},
    }
    output_schema: ClassVar = {
        "type": "object",
        "properties": {"answer": {"type": "string"}},
    }

    def __init__(self):
        self.name = "search"
        self.description = "Busca documentos"
        self.annotations = {"readOnlyHint": True, "unknown": "must-not-persist"}

    @property
    def inputSchema(self):  # noqa: N802 - alias definido pelo protocolo MCP
        return self.input_schema

    @property
    def outputSchema(self):  # noqa: N802 - alias definido pelo protocolo MCP
        return self.output_schema


class _FakeSession:
    _protocol_version = "2025-06-18"

    def __init__(self, calls, functions=None):
        self.calls = calls
        self.functions = functions or [_Function()]

    async def list_tools(self, *, params=None):
        cursor = getattr(params, "cursor", None) if params is not None else None
        self.calls.append(("tools/list", {"cursor": cursor}))
        if cursor is None:
            return SimpleNamespace(tools=self.functions, nextCursor="page-2")
        assert cursor == "page-2"
        return SimpleNamespace(tools=[], nextCursor=None)


class _FakeMcp:
    protocol_version = "2025-06-18"
    functions: ClassVar[list] = []

    def __init__(self, calls, functions=None, **kwargs):
        self.calls = calls
        self.calls.append(("construct", kwargs))
        self.session = _FakeSession(calls, functions)

    async def __aenter__(self):
        self.calls.append(("initialize", None))
        return self

    async def __aexit__(self, *_args):
        self.calls.append(("close", None))

    async def load_tools(self):
        from mcp.types import PaginatedRequestParams

        result = await self.session.list_tools(params=None)
        while result.nextCursor:
            result = await self.session.list_tools(
                params=PaginatedRequestParams(cursor=result.nextCursor)
            )


async def _discovery_test() -> None:
    calls = []
    evidence_store = InMemoryEvidenceStore()

    def resolver(name, version):
        assert (name, version) == ("tenant-tools", "2")
        return {
            "name": "tenant-a-tenant-tools",
            "id": "tb-1",
            "version": "2",
            "url": "https://example.test/toolboxes/tenant-a-tenant-tools/versions/2/mcp",
        }

    result = await discover_toolbox(
        "tenant-tools",
        "2",
        toolbox_resolver=resolver,
        mcp_factory=lambda **kwargs: _FakeMcp(calls, **kwargs),
        evidence_store=evidence_store,
    )
    methods = [name for name, _ in calls]
    assert methods == ["construct", "initialize", "tools/list", "tools/list", "close"]
    assert "tools/call" not in methods
    construct = calls[0][1]
    assert construct["load_tools"] is False
    assert construct["load_prompts"] is False
    assert construct["request_timeout"] == 10
    assert result["resolvedVersion"] == "2"
    assert result["protocolVersion"] == "2025-06-18"
    assert result["tools"] == [
        {"name": "search", "description": "Busca documentos", "hash": result["tools"][0]["hash"]}
    ]
    snapshot = read_evidence(result["snapshotId"], scope="self-hosted", store=evidence_store)
    assert snapshot is not None
    assert snapshot["tenantKey"] == "self-hosted"
    assert snapshot["tools"][0]["annotations"] == {"readOnlyHint": True}
    assert "unknown" not in json.dumps(snapshot)
    reordered = {
        "description": "Busca documentos",
        "name": "search",
        "annotations": {"readOnlyHint": True},
        "outputSchema": _Function.output_schema,
        "inputSchema": _Function.input_schema,
    }
    assert snapshot["tools"][0]["contractHash"] == hashlib.sha256(rfc8785.dumps(reordered)).hexdigest()

    write_evidence("same-id", {"tenant": "a"}, scope="tenant-a", store=evidence_store)
    write_evidence("same-id", {"tenant": "b"}, scope="tenant-b", store=evidence_store)
    assert read_evidence("same-id", scope="tenant-a", store=evidence_store) == {"tenant": "a"}
    assert read_evidence("same-id", scope="tenant-b", store=evidence_store) == {"tenant": "b"}

    deep_schema = {"type": "string"}
    for _ in range(13):
        deep_schema = {"items": deep_schema}
    deep_tool = _Function()
    deep_tool.input_schema = deep_schema
    try:
        await discover_toolbox(
            "tenant-tools",
            "2",
            toolbox_resolver=resolver,
            mcp_factory=lambda **kwargs: _FakeMcp([], [deep_tool], **kwargs),
            evidence_store=evidence_store,
        )
        raise AssertionError("schema profundo deveria invalidar a discovery")
    except DiscoveryRejected:
        pass

    tenant_results = {}
    for tenant in ("tenant-a", "tenant-b"):
        set_current_tenant(SimpleNamespace(tid=tenant))

        def tenant_resolver(name, version):
            assert (name, version) == ("shared-tools", "1")
            tenant_id = current_tenant_id()
            return {
                "name": f"{tenant_id}-shared-tools",
                "id": f"{tenant_id}-toolbox",
                "version": "1",
                "url": f"https://example.test/{tenant_id}/shared-tools/1/mcp",
            }

        tenant_results[tenant] = await discover_toolbox(
            "shared-tools",
            "1",
            toolbox_resolver=tenant_resolver,
            mcp_factory=lambda **kwargs: _FakeMcp([], **kwargs),
            evidence_store=evidence_store,
        )

    assert tenant_results["tenant-a"]["source"] != tenant_results["tenant-b"]["source"]
    tenant_a_snapshot = tenant_results["tenant-a"]["snapshotId"]
    assert get_snapshot(tenant_a_snapshot, evidence_store=evidence_store) is None
    set_current_tenant(SimpleNamespace(tid="tenant-a"))
    assert get_snapshot(tenant_a_snapshot, evidence_store=evidence_store) is not None
    set_current_tenant(None)


def main() -> int:
    client = _Client()
    result = list_toolbox_projection(
        25,
        "page-1",
        client_factory=lambda: client,
    )
    assert result == {
        "items": [
            {
                "name": "tenant-tools",
                "description": "atual",
                "defaultVersion": "2",
                "versions": [
                    {"version": "1", "createdAt": "2026-08-30T10:00:00+00:00"},
                    {"version": "2", "createdAt": "2026-08-31T10:00:00+00:00"},
                ],
                "mcpUrl": (
                    "https://example.services.ai.azure.com/api/projects/tenant/"
                    "toolboxes/tenant-tools/mcp?api-version=v1"
                ),
            }
        ],
        "nextCursor": "next-page",
    }
    assert client.closed

    evidence_store = InMemoryEvidenceStore()
    receipt = write_evidence(
        "msnap_test",
        {"source": "tenant-tools", "tools": [{"name": "search"}]},
        store=evidence_store,
    )
    assert receipt["id"] == "msnap_test"
    assert receipt["bytes"] > 0
    assert receipt["written"] is True
    assert read_evidence("msnap_test", store=evidence_store) == {
        "source": "tenant-tools",
        "tools": [{"name": "search"}],
    }
    try:
        write_evidence("msnap_test", {}, store=evidence_store)
        raise AssertionError("evidence overwrite should fail")
    except EvidenceExists:
        pass
    asyncio.run(_discovery_test())
    print("mcp toolbox projection: ok")
    return 0


if __name__ == "__main__":
    sys.exit(main())
