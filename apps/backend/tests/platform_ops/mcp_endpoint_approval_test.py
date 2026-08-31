"""F03: proposta inerte e decisão Admin auditável de endpoint MCP."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.modules.platform_ops.public import (
    EndpointConflict,
    InMemoryEndpointStore,
    approve_mcp_endpoint,
    create_mcp_endpoint,
    get_mcp_endpoint,
    list_mcp_endpoints,
)
from app.modules.tenancy.public import set_current_tenant


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    store = InMemoryEndpointStore()
    events: list[dict] = []
    network_calls: list[str] = []

    def recorder(**event):
        events.append(event)
        return {"hash": "audit-hash"}

    set_current_tenant(SimpleNamespace(tid="tenant-a"))
    try:
        endpoint = create_mcp_endpoint(
            {"url": "https://mcp.example.test/service", "auth": {"mode": "public"}},
            store=store,
            network_probe=lambda *_args: network_calls.append("called"),
        )
        check("proposal starts pending", endpoint["status"] == "pending")
        check("proposal is inert", network_calls == [])
        check("origin is canonical", endpoint["origin"] == "https://mcp.example.test/service")
        check("tenant is not exposed", "tenantKey" not in endpoint)
        check("list is tenant scoped", list_mcp_endpoints(store=store) == [endpoint])

        approved = approve_mcp_endpoint(
            endpoint["id"],
            decision="approved",
            reason="origem corporativa validada",
            store=store,
            audit_recorder=recorder,
            actor="human:admin",
        )
        check("Admin decision changes state", approved["status"] == "approved")
        check("decision has its own revision", approved["revision"] == 2)
        check("approval is audited once", len(events) == 1)
        check("audit kind is approval", events[0]["kind"] == "approval")
        check("audit contains no URL", "https://" not in repr(events[0]))

        try:
            approve_mcp_endpoint(
                endpoint["id"],
                decision="rejected",
                reason="replay",
                store=store,
                audit_recorder=recorder,
                actor="human:admin",
            )
        except EndpointConflict:
            check("immutable decision rejects replay", True)
        else:
            check("immutable decision rejects replay", False)

        set_current_tenant(SimpleNamespace(tid="tenant-b"))
        check("cross-tenant endpoint looks absent", get_mcp_endpoint(endpoint["id"], store=store) is None)
        tenant_b = create_mcp_endpoint(
            {"url": "https://mcp.example.test/service", "auth": {"mode": "public"}},
            store=store,
        )
        check("same origin has tenant-local identity", tenant_b["id"] != endpoint["id"])
    finally:
        set_current_tenant(None)

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
