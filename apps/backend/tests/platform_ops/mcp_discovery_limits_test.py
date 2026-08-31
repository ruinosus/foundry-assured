"""F07: limites remotos invalidam a discovery inteira antes de persistir."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace
from typing import Any

import rfc8785

from app.modules.audit.public import InMemoryEvidenceStore, read_evidence
from app.modules.platform_ops.public import (
    DiscoveryLimitExceeded,
    DiscoveryRejected,
    InMemoryMcpSourceStore,
    discover_toolbox,
)


def _tool(
    name: str = "tool",
    *,
    description: str = "",
    schema: Any = None,
) -> dict[str, Any]:
    return {
        "name": name,
        "description": description,
        "inputSchema": schema if schema is not None else {"type": "object"},
    }


class _Session:
    _protocol_version = "2025-06-18"

    def __init__(self, pages: list[tuple[list[dict[str, Any]], str | None]]) -> None:
        self.pages = pages
        self.calls = 0

    async def list_tools(self, *, params=None):
        del params
        tools, cursor = self.pages[self.calls]
        self.calls += 1
        return SimpleNamespace(tools=tools, nextCursor=cursor)


class _Mcp:
    def __init__(self, pages, **_kwargs) -> None:
        self.session = _Session(pages)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *_args):
        return None

    async def load_tools(self) -> None:
        from mcp.types import PaginatedRequestParams

        page = await self.session.list_tools(params=None)
        while page.nextCursor:
            page = await self.session.list_tools(
                params=PaginatedRequestParams(cursor=page.nextCursor)
            )


def _source(_name: str, _version: str) -> dict:
    return {
        "id": "tb-adversarial",
        "name": "adversarial",
        "version": "1",
        "url": "https://example.test/adversarial/mcp",
    }


async def _discover(
    pages: list[tuple[list[dict[str, Any]], str | None]],
    *,
    evidence: InMemoryEvidenceStore | None = None,
) -> tuple[dict, InMemoryEvidenceStore]:
    target = evidence or InMemoryEvidenceStore()
    result = await discover_toolbox(
        "adversarial",
        "1",
        toolbox_resolver=_source,
        mcp_factory=lambda **kwargs: _Mcp(pages, **kwargs),
        evidence_store=target,
        source_store=InMemoryMcpSourceStore(),
        audit_recorder=lambda **_kwargs: None,
    )
    return result, target


async def _rejects_without_write(
    pages: list[tuple[list[dict[str, Any]], str | None]],
    expected: type[Exception] = DiscoveryRejected,
) -> bool:
    evidence = InMemoryEvidenceStore()
    try:
        await _discover(pages, evidence=evidence)
    except expected:
        return not evidence._items
    return False


def _schema_with_size(size: int) -> dict[str, Any]:
    base = {"type": "string", "title": ""}
    padding = size - len(rfc8785.dumps(base))
    assert padding >= 0
    result = {**base, "title": "x" * padding}
    assert len(rfc8785.dumps(result)) == size
    return result


def _nested_schema(wrappers: int) -> dict[str, Any]:
    schema: dict[str, Any] = {"type": "string"}
    for _ in range(wrappers):
        schema = {"items": schema}
    return schema


async def _run() -> dict[str, bool]:
    checks: dict[str, bool] = {}

    boundary_tools = [_tool(f"t{index:03}") for index in range(200)]
    result, _ = await _discover([(boundary_tools, None)])
    checks["200 tools são aceitas"] = len(result["tools"]) == 200
    checks["201 tools são rejeitadas sem snapshot"] = await _rejects_without_write(
        [(boundary_tools + [_tool("overflow")], None)], DiscoveryLimitExceeded
    )

    properties_200 = {f"p{index}": {"type": "string"} for index in range(200)}
    result, _ = await _discover(
        [([_tool(schema={"type": "object", "properties": properties_200})], None)]
    )
    checks["200 propriedades são aceitas"] = len(result["tools"]) == 1
    properties_201 = {**properties_200, "overflow": {"type": "string"}}
    checks["201 propriedades são rejeitadas sem snapshot"] = await _rejects_without_write(
        [([_tool(schema={"type": "object", "properties": properties_201})], None)],
        DiscoveryLimitExceeded,
    )

    result, _ = await _discover([([_tool(schema=_nested_schema(10))], None)])
    checks["profundidade 12 é aceita"] = len(result["tools"]) == 1
    checks["profundidade 13 é rejeitada sem snapshot"] = await _rejects_without_write(
        [([_tool(schema=_nested_schema(11))], None)], DiscoveryLimitExceeded
    )

    result, _ = await _discover([([_tool("n" * 128, description="d" * 2048)], None)])
    checks["nome 128 e descrição 2048 são aceitos"] = len(result["tools"]) == 1
    checks["nome 129 é rejeitado sem snapshot"] = await _rejects_without_write(
        [([_tool("n" * 129)], None)], DiscoveryLimitExceeded
    )
    checks["descrição 2049 é rejeitada sem snapshot"] = await _rejects_without_write(
        [([_tool(description="d" * 2049)], None)], DiscoveryLimitExceeded
    )

    result, _ = await _discover([([_tool(schema=_schema_with_size(32 * 1024))], None)])
    checks["schema de 32 KiB é aceito"] = len(result["tools"]) == 1
    checks["schema acima de 32 KiB é rejeitado sem snapshot"] = await _rejects_without_write(
        [([_tool(schema=_schema_with_size(32 * 1024 + 1))], None)],
        DiscoveryLimitExceeded,
    )

    repeated_pages = [([_tool("first")], "repeated"), ([_tool("second")], "repeated")]
    checks["cursor repetido é rejeitado sem snapshot"] = await _rejects_without_write(
        repeated_pages
    )
    checks["página sem progresso é rejeitada sem snapshot"] = await _rejects_without_write(
        [([], "next")]
    )
    checks["tool duplicada é rejeitada sem snapshot"] = await _rejects_without_write(
        [([_tool("same"), _tool("same")], None)]
    )
    checks["schema inválido é rejeitado sem snapshot"] = await _rejects_without_write(
        [([_tool(schema=["not-an-object"])], None)]
    )

    baseline_tools = [_tool(f"s{index:03}") for index in range(130)]
    baseline_result, baseline_store = await _discover([(baseline_tools, None)])
    baseline = read_evidence(
        baseline_result["snapshotId"], scope="self-hosted", store=baseline_store
    )
    assert baseline is not None
    padding = 256 * 1024 - len(rfc8785.dumps(baseline))
    assert 0 < padding <= len(baseline_tools) * 2048
    for tool in baseline_tools:
        added = min(2048, padding)
        tool["description"] = "d" * added
        padding -= added
    assert padding == 0
    exact_result, exact_store = await _discover([(baseline_tools, None)])
    exact = read_evidence(
        exact_result["snapshotId"], scope="self-hosted", store=exact_store
    )
    checks["snapshot de 256 KiB é aceito"] = (
        exact is not None and len(rfc8785.dumps(exact)) == 256 * 1024
    )
    for tool in baseline_tools:
        if len(tool["description"]) < 2048:
            tool["description"] += "d"
            break
    checks["snapshot acima de 256 KiB é rejeitado sem parcial"] = (
        await _rejects_without_write([(baseline_tools, None)], DiscoveryLimitExceeded)
    )
    return checks


def main() -> int:
    checks = asyncio.run(_run())
    failures = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
