"""F02: contrato estrito do documento mcp-binding."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient

from app.modules.audit.public import InMemoryEvidenceStore, write_evidence
from app.modules.okf.public import AuthoringInvalid, parse_authoring_document
from app.modules.platform_ops.public import (
    InMemoryRegistryBindingStore,
    RegistryBindingInvalid,
    RegistryBindingScope,
    RegistryBindingService,
)
from app.modules.tenancy.public import (
    AuthoringArea,
    TenantConfig,
    TenantRecord,
    current_authoring_scope_key,
    resolve_area,
    set_current_tenant,
)


def _document(spec: dict[str, Any]) -> str:
    header = {
        "type": "mcp-binding",
        "status": "draft",
        "generated": {"by": "process:mcp-binding-test", "at": "2026-08-31T12:00:00Z"},
        "x-foundry-authoring": {
            "profile_version": "1",
            "id": "platform-mcp",
            "revision": "1",
            "publication_state": "proposed",
            "tenant": "tenant-a",
            "area": "platform",
            "spec": spec,
        },
    }
    return f"---\n{yaml.safe_dump(header, sort_keys=False).rstrip()}\n---\n\n# MCP binding\n"


def _valid(**overrides: Any) -> dict[str, Any]:
    spec = {
        "toolbox": {"name": "platform-tools", "version": "3"},
        "tools": ["search_resources", "update_resource"],
        "reviewedSnapshot": {"id": "msnap_reviewed", "hash": "a" * 64},
    }
    spec.update(overrides)
    return {key: value for key, value in spec.items() if value is not None}


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    def accepts(name: str, spec: dict[str, Any]) -> None:
        try:
            parse_authoring_document(_document(spec), where=name)
        except AuthoringInvalid:
            check(name, False)
        else:
            check(name, True)

    def refuses(name: str, spec: dict[str, Any]) -> None:
        try:
            parse_authoring_document(_document(spec), where=name)
        except AuthoringInvalid:
            check(name, True)
        else:
            check(name, False)

    accepts("fixed Toolbox version", _valid())
    accepts(
        "default Toolbox version",
        _valid(toolbox={"name": "platform-tools", "useDefault": True}),
    )
    accepts(
        "approved endpoint reference",
        _valid(endpoint={"id": "mep_approved"}, toolbox=None),
    )

    refuses("exactly one source is required", {key: value for key, value in _valid().items() if key != "toolbox"})
    refuses("two sources are ambiguous", _valid(endpoint={"id": "mep_approved"}))
    refuses(
        "Toolbox version and default are exclusive",
        _valid(toolbox={"name": "platform-tools", "version": "3", "useDefault": True}),
    )
    refuses("useDefault must be true", _valid(toolbox={"name": "platform-tools", "useDefault": False}))
    refuses("tools cannot be empty", _valid(tools=[]))
    refuses("tools must be unique", _valid(tools=["search_resources", "search_resources"]))
    refuses(
        "snapshot hash must be lowercase SHA-256",
        _valid(reviewedSnapshot={"id": "msnap_reviewed", "hash": "A" * 64}),
    )
    refuses("unknown fields fail", _valid(executable=True))
    refuses("classification was removed", _valid(classification=[]))
    refuses("connection was removed", _valid(toolbox={"name": "platform-tools", "version": "3", "connection": "ops"}))
    refuses("URL was removed", _valid(endpoint={"id": "mep_approved", "url": "https://example.test"}, toolbox=None))
    refuses("recursive secret-like keys fail", _valid(metadata={"nested": [{"clientSecret": "canary"}]}))

    store = InMemoryRegistryBindingStore()
    connections = {
        "tenant-a": {"conn-platform"},
        "tenant-b": {"conn-other"},
    }

    def connection_exists(tenant_id: str, connection_id: str) -> bool:
        return connection_id in connections.get(tenant_id, set())

    def conform(spec: dict[str, Any]) -> dict[str, Any]:
        blocked = spec["tools"] == ["missing_tool"]
        return {
            "status": "block" if blocked else "pass",
            "reasons": ["MCP_TOOL_NOT_FOUND"] if blocked else [],
            "source": {
                "kind": "toolbox",
                "id": "tb-platform",
                "name": "platform-tools",
                "resolvedVersion": "3",
            },
            "snapshot": spec["reviewedSnapshot"],
            "tools": [
                {
                    "name": name,
                    "status": "block" if blocked else "pass",
                    "effectiveEffect": "quarantined" if blocked else "read",
                }
                for name in spec["tools"]
            ],
            "runtime": {"allowedTools": [] if blocked else spec["tools"]},
        }

    service = RegistryBindingService(
        store,
        connection_exists=connection_exists,
        conformity_evaluator=conform,
    )
    scope_a = RegistryBindingScope("tenant-a", "area-a")
    created = service.put(
        scope_a,
        {
            "id": "platform-search",
            "name": "Platform search",
            "connectionId": "conn-platform",
            "risk": "read",
            "binding": _valid(tools=["search_resources"]),
        },
        actor="admin-a",
    )
    check("new binding awaits review", created["status"] == "pending_review")
    check("binding stores concrete references", created["source"]["resolvedVersion"] == "3")
    check("owner area lists its binding", service.list(scope_a)["items"] == [created])
    check(
        "another area sees no binding",
        service.list(RegistryBindingScope("tenant-a", "area-b"))["items"] == [],
    )
    check(
        "another tenant sees no binding",
        service.list(RegistryBindingScope("tenant-b", "area-a"))["items"] == [],
    )

    def rejects(name: str, proposal: dict[str, Any]) -> None:
        try:
            service.put(scope_a, proposal, actor="admin-a")
        except RegistryBindingInvalid:
            check(name, True)
        else:
            check(name, False)

    rejects(
        "cross-tenant connection fails closed",
        {
            "id": "cross-connection",
            "name": "Cross connection",
            "connectionId": "conn-other",
            "risk": "read",
            "binding": _valid(),
        },
    )
    rejects(
        "secret-like fields never enter the store",
        {
            "id": "secret-binding",
            "name": "Secret binding",
            "connectionId": "conn-platform",
            "risk": "read",
            "binding": {**_valid(), "metadata": {"token": "canary"}},
        },
    )
    blocked = service.put(
        scope_a,
        {
            "id": "missing-tool",
            "name": "Missing tool",
            "connectionId": "conn-platform",
            "risk": "write",
            "binding": _valid(tools=["missing_tool"]),
        },
        actor="admin-a",
    )
    check("incompatible implementation is blocked", blocked["status"] == "blocked")
    check("only affected capability is quarantined", blocked["tools"][0]["status"] == "block")

    failing_store = InMemoryRegistryBindingStore()
    audit_failed = RegistryBindingService(
        failing_store,
        connection_exists=connection_exists,
        conformity_evaluator=conform,
        audit_recorder=lambda **_kwargs: (_ for _ in ()).throw(RuntimeError("audit unavailable")),
    )
    try:
        audit_failed.put(
            scope_a,
            {
                "id": "audit-failure",
                "name": "Audit failure",
                "connectionId": "conn-platform",
                "risk": "read",
                "binding": _valid(),
            },
            actor="admin-a",
        )
    except RuntimeError:
        pass
    check(
        "audit failure prevents persistence",
        audit_failed.list(scope_a)["items"] == [],
    )

    from app.modules.platform_ops import api as platform_api

    application = FastAPI()
    application.include_router(platform_api.router)
    application.dependency_overrides[platform_api.require_area] = lambda: None
    application.dependency_overrides[platform_api._registry_service] = lambda: service
    platform_api.current_area = lambda: SimpleNamespace(id="area-a")
    platform_api.current_tenant_id = lambda: "tenant-a"
    platform_api.current_user = lambda: SimpleNamespace(oid="admin-a")
    client = TestClient(application)
    api_payload = {
        "id": "api-binding",
        "name": "API binding",
        "connectionId": "conn-platform",
        "risk": "read",
        "binding": _valid(),
    }
    response = client.post(
        "/authoring/registry-bindings",
        headers={"X-Area-ID": "area-a"},
        json=api_payload,
    )
    check(
        "admin API creates an inactive area-scoped binding",
        response.status_code == 201 and response.json()["status"] == "pending_review",
    )
    listed = client.get(
        "/authoring/registry-bindings", headers={"X-Area-ID": "area-a"}
    )
    check(
        "admin API lists only the current area",
        listed.status_code == 200
        and "api-binding" in {item["id"] for item in listed.json()["items"]},
    )
    cross_area = client.get(
        "/authoring/registry-bindings", headers={"X-Area-ID": "area-b"}
    )
    check("cross-area API read fails closed", cross_area.status_code == 404)
    registry_routes = [
        route
        for route in application.routes
        if isinstance(route, APIRoute) and "registry-bindings" in route.path
    ]
    check(
        "every registry route mounts role and area gates",
        len(registry_routes) == 3
        and all(len(route.dependant.dependencies) >= 3 for route in registry_routes),
    )
    admin_dependency = platform_api._admin[0].dependency
    application.dependency_overrides[admin_dependency] = lambda: (_ for _ in ()).throw(
        HTTPException(403, "ROLE_REQUIRED")
    )
    forbidden = client.get(
        "/authoring/registry-bindings", headers={"X-Area-ID": "area-a"}
    )
    check("user without Admin receives 403", forbidden.status_code == 403)
    application.dependency_overrides.pop(admin_dependency)
    platform_api.current_connection = lambda _connection_id: None
    missing_connection = client.post(
        "/authoring/mcp-endpoints",
        json={
            "url": "https://mcp.example.test",
            "auth": {"mode": "connection", "connectionRef": "missing"},
        },
    )
    check(
        "endpoint refuses an unresolved area connection before persistence",
        missing_connection.status_code == 422,
    )
    toolbox_routes = [
        route
        for route in application.routes
        if isinstance(route, APIRoute) and route.path == "/authoring/toolboxes"
    ]
    check(
        "Toolbox inventory mounts Admin and area gates",
        len(toolbox_routes) == 1
        and {
            dependency.call
            for dependency in toolbox_routes[0].dependant.dependencies
        }
        >= {admin_dependency, platform_api.require_area},
    )

    from app.modules.platform_ops.internal import mcp_discovery

    tenant = TenantRecord(
        tid="tenant-a",
        name="Tenant A",
        tier="shared",
        status="active",
        data_plane=TenantConfig(),
        areas=(
            AuthoringArea("area-a", "Area A", ("group-a",)),
            AuthoringArea("area-b", "Area B", ("group-b",)),
        ),
    )
    set_current_tenant(SimpleNamespace(tid="tenant-a"))
    user_a = SimpleNamespace(tid="tenant-a", roles=["Admin"], groups=["group-a"])
    user_b = SimpleNamespace(tid="tenant-a", roles=["Admin"], groups=["group-b"])
    resolve_area(user_a, tenant, "area-a")
    snapshot_id = "msnap_area_isolation"
    snapshot = {
        "snapshotId": snapshot_id,
        "tenantKey": current_authoring_scope_key(),
        "source": {"kind": "toolbox", "id": "tb-platform", "resolvedVersion": "3"},
        "snapshotHash": "a" * 64,
        "tools": [],
    }
    evidence_store = InMemoryEvidenceStore()
    write_evidence(
        snapshot_id,
        snapshot,
        scope=current_authoring_scope_key(),
        store=evidence_store,
    )
    mcp_discovery._PROJECTIONS[(current_authoring_scope_key(), snapshot_id)] = {
        "snapshotId": snapshot_id,
        "source": snapshot["source"],
        "hash": snapshot["snapshotHash"],
        "tools": [],
    }
    check(
        "owner area reads its MCP snapshot",
        mcp_discovery.get_snapshot(snapshot_id, evidence_store=evidence_store) is not None,
    )
    resolve_area(user_b, tenant, "area-b")
    check(
        "cross-area MCP snapshot looks absent",
        mcp_discovery.get_snapshot(snapshot_id, evidence_store=evidence_store) is None,
    )
    resolve_area(SimpleNamespace(tid="tenant-a", roles=[], groups=[]), tenant, "area-a")
    set_current_tenant(None)

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
