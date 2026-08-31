"""F02: conformidade tenant-safe entre binding, Toolbox e snapshot revisado."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.modules.foundry.public import resolve_toolbox_default_version
from app.modules.platform_ops.public import (
    ConformityNotFound,
    evaluate_mcp_binding,
)
from app.modules.tenancy.public import set_current_tenant


class _Toolboxes:
    def get(self, name: str):
        return SimpleNamespace(
            name=name,
            id="tb-platform",
            default_version=SimpleNamespace(version="3"),
        )

    def list_versions(self, _name: str):
        return [SimpleNamespace(version="2"), SimpleNamespace(version="3")]


class _Client:
    endpoint = "https://example.services.ai.azure.com/api/projects/tenant-a"

    def __init__(self) -> None:
        self.toolboxes = _Toolboxes()
        self.closed = False

    def close(self) -> None:
        self.closed = True


def _fixed(hash_value: str = "a" * 64) -> dict:
    return {
        "toolbox": {"name": "platform-tools", "version": "3"},
        "tools": ["search_resources"],
        "reviewedSnapshot": {"id": "msnap_reviewed", "hash": hash_value},
    }


def _snapshot(*, tenant: str = "tenant-a", version: str = "3") -> dict:
    if tenant != "tenant-a":
        raise AssertionError("snapshot cross-tenant não pode ser lido")
    return {
        "snapshotId": "msnap_reviewed",
        "source": {
            "kind": "toolbox",
            "id": "tb-platform",
            "name": "tenant-a-platform-tools",
            "resolvedVersion": version,
        },
        "hash": "a" * 64,
        "tools": [
            {"name": "search_resources", "description": "Busca recursos", "hash": "b" * 64},
            {"name": "update_resource", "description": "Atualiza recurso", "hash": "c" * 64},
        ],
    }


def _resolve(name: str, version: str) -> dict:
    assert (name, version) == ("platform-tools", "3")
    return {
        "kind": "toolbox",
        "id": "tb-platform",
        "name": "tenant-a-platform-tools",
        "version": "3",
    }


def _default(name: str) -> dict:
    assert name == "platform-tools"
    return _resolve(name, "3")


def _runtime(_snapshot_id: str, tool_names: list[str], *, current: bool) -> dict:
    effect = "read" if current else "quarantined"
    return {
        "allowedTools": list(tool_names) if current else [],
        "approvalMode": {
            "always_require_approval": [],
            "never_require_approval": list(tool_names) if current else [],
        },
        "tools": [
            {"name": name, "effect": effect, "allowed": current}
            for name in tool_names
        ],
    }


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    set_current_tenant(SimpleNamespace(tid="tenant-a"))
    try:
        client = _Client()
        official_default = resolve_toolbox_default_version(
            "platform-tools", client_factory=lambda: client
        )
        check("official default version is observed", official_default["version"] == "3")
        check("official Toolbox client is closed", client.closed)

        passed = evaluate_mcp_binding(
            _fixed(),
            toolbox_resolver=_resolve,
            toolbox_default_resolver=_default,
            snapshot_reader=lambda _snapshot_id: _snapshot(),
            runtime_resolver=_runtime,
        )
        check("fixed reviewed binding passes", passed["status"] == "pass")
        check("pass has stable empty reasons", passed["reasons"] == [])
        check("resolved source is returned", passed["source"]["resolvedVersion"] == "3")
        check("reviewed snapshot is returned", passed["snapshot"] == {"id": "msnap_reviewed", "hash": "a" * 64})
        check(
            "selected tools are conformant",
            passed["tools"]
            == [
                {
                    "name": "search_resources",
                    "status": "pass",
                    "effectiveEffect": "read",
                }
            ],
        )
        check("runtime allowlist is derived", passed["runtime"]["allowedTools"] == ["search_resources"])

        defaulted = evaluate_mcp_binding(
            {
                **_fixed(),
                "toolbox": {"name": "platform-tools", "useDefault": True},
            },
            toolbox_resolver=_resolve,
            toolbox_default_resolver=_default,
            snapshot_reader=lambda _snapshot_id: _snapshot(),
            runtime_resolver=_runtime,
        )
        check("default resolves observed version", defaulted["source"]["resolvedVersion"] == "3")
        check("default blocks until fixed materialization", defaulted["status"] == "block")
        check(
            "default reason is stable",
            defaulted["reasons"] == ["MCP_DEFAULT_VERSION_REQUIRES_PIN"],
        )

        stale_hash = evaluate_mcp_binding(
            _fixed("d" * 64),
            toolbox_resolver=_resolve,
            toolbox_default_resolver=_default,
            snapshot_reader=lambda _snapshot_id: _snapshot(),
            runtime_resolver=_runtime,
        )
        check("snapshot hash mismatch blocks", stale_hash["status"] == "block")
        check("snapshot mismatch reason is stable", stale_hash["reasons"] == ["MCP_SNAPSHOT_STALE"])

        missing_tool = evaluate_mcp_binding(
            {**_fixed(), "tools": ["invented_tool"]},
            toolbox_resolver=_resolve,
            toolbox_default_resolver=_default,
            snapshot_reader=lambda _snapshot_id: _snapshot(),
            runtime_resolver=_runtime,
        )
        check("tool outside snapshot blocks", missing_tool["status"] == "block")
        check("missing tool reason is stable", missing_tool["reasons"] == ["MCP_TOOL_NOT_FOUND"])

        wrong_source = evaluate_mcp_binding(
            _fixed(),
            toolbox_resolver=_resolve,
            toolbox_default_resolver=_default,
            snapshot_reader=lambda _snapshot_id: _snapshot(version="2"),
            runtime_resolver=_runtime,
        )
        check("snapshot from another source version blocks", wrong_source["status"] == "block")
        check("source mismatch reason is stable", wrong_source["reasons"] == ["MCP_SNAPSHOT_STALE"])

        try:
            endpoint_binding = _fixed()
            endpoint_binding.pop("toolbox")
            endpoint_binding["endpoint"] = {"id": "mep_pending_f03"}
            evaluate_mcp_binding(
                endpoint_binding,
                toolbox_resolver=_resolve,
                toolbox_default_resolver=_default,
                snapshot_reader=lambda _snapshot_id: _snapshot(),
                runtime_resolver=_runtime,
            )
        except ConformityNotFound:
            check("endpoint is fail-closed until F03", True)
        else:
            check("endpoint is fail-closed until F03", False)

        set_current_tenant(SimpleNamespace(tid="tenant-b"))
        try:
            evaluate_mcp_binding(
                _fixed(),
                toolbox_resolver=_resolve,
                toolbox_default_resolver=_default,
                snapshot_reader=lambda _snapshot_id: None,
                runtime_resolver=_runtime,
            )
        except ConformityNotFound as exc:
            check("cross-tenant snapshot looks absent", str(exc) == "MCP_SOURCE_NOT_FOUND")
        else:
            check("cross-tenant snapshot looks absent", False)
    finally:
        set_current_tenant(None)

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
