"""F03: egress fail-closed, DNS público e lease de discovery por source."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from app.modules.platform_ops.public import (
    DiscoveryBusy,
    EgressDenied,
    InMemoryDiscoveryLeaseStore,
    InMemoryEndpointStore,
    approve_mcp_endpoint,
    create_mcp_endpoint,
    discover_endpoint,
    validate_mcp_origin,
)
from app.modules.tenancy.public import set_current_tenant


def _approved(store: InMemoryEndpointStore) -> dict:
    endpoint = create_mcp_endpoint(
        {"url": "https://mcp.example.test/service", "auth": {"mode": "public"}},
        store=store,
    )
    return approve_mcp_endpoint(
        endpoint["id"],
        decision="approved",
        reason="teste",
        store=store,
        audit_recorder=lambda **_event: {"hash": "audit"},
        actor="human:admin",
    )


async def _discovery_checks(check) -> None:
    endpoint_store = InMemoryEndpointStore()
    lease_store = InMemoryDiscoveryLeaseStore()
    endpoint = _approved(endpoint_store)
    resolutions: list[str] = []
    calls: list[dict] = []

    async def discovery(source, **kwargs):
        calls.append({"source": source, **kwargs})
        return {"snapshotId": "msnap_endpoint", "source": source}

    def public_dns(host: str, port: int):
        resolutions.append(f"{host}:{port}")
        return ["20.42.1.10", "2603:1030:20e:3::10"]

    result = await discover_endpoint(
        endpoint["id"],
        endpoint_store=endpoint_store,
        lease_store=lease_store,
        resolver=public_dns,
        discovery=discovery,
    )
    check("approved endpoint reaches discovery", result["snapshotId"] == "msnap_endpoint")
    check("DNS is resolved immediately before connect", resolutions == ["mcp.example.test:443"])
    check("redirects are disabled", calls[0]["follow_redirects"] is False)
    check("public mode sends no auth provider", calls[0]["header_provider"] is None)

    lease_store.acquire("tenant-a", endpoint["id"], ttl_seconds=30)
    try:
        await discover_endpoint(
            endpoint["id"],
            endpoint_store=endpoint_store,
            lease_store=lease_store,
            resolver=public_dns,
            discovery=discovery,
        )
    except DiscoveryBusy:
        check("concurrent discovery is busy", True)
    else:
        check("concurrent discovery is busy", False)

    now = [100.0]
    expiring = InMemoryDiscoveryLeaseStore(clock=lambda: now[0])
    expiring.acquire("tenant-a", endpoint["id"], ttl_seconds=30)
    now[0] += 31
    try:
        expiring.acquire("tenant-a", endpoint["id"], ttl_seconds=30)
    except DiscoveryBusy:
        check("lease expires after 30 seconds", False)
    else:
        check("lease expires after 30 seconds", True)

    set_current_tenant(SimpleNamespace(tid="tenant-b"))
    try:
        await discover_endpoint(
            endpoint["id"],
            endpoint_store=endpoint_store,
            lease_store=InMemoryDiscoveryLeaseStore(),
            resolver=public_dns,
            discovery=discovery,
        )
    except EgressDenied as exc:
        check("cross-tenant source looks absent", str(exc) == "MCP_SOURCE_NOT_FOUND")
    else:
        check("cross-tenant source looks absent", False)
    finally:
        set_current_tenant(SimpleNamespace(tid="tenant-a"))


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    denied = (
        "http://mcp.example.test/service",
        "https://127.0.0.1/service",
        "https://[::1]/service",
        "https://user@mcp.example.test/service",
        "https://mcp.example.test:8443/service",
        "https://mcp.example.test/service?token=canary",
        "https://mcp.example.test/service#fragment",
    )
    for origin in denied:
        try:
            validate_mcp_origin(origin)
        except EgressDenied:
            check(f"origin denied: {origin.split(':', 1)[0]}", True)
        else:
            check(f"origin denied: {origin.split(':', 1)[0]}", False)

    for address in (
        "127.0.0.1", "10.0.0.1", "169.254.169.254", "224.0.0.1",
        "::1", "fc00::1", "fe80::1", "ff02::1",
    ):
        try:
            validate_mcp_origin(
                "https://mcp.example.test/service",
                resolver=lambda _host, _port, address=address: [address],
                resolve=True,
            )
        except EgressDenied:
            check(f"address denied: {address}", True)
        else:
            check(f"address denied: {address}", False)

    set_current_tenant(SimpleNamespace(tid="tenant-a"))
    try:
        asyncio.run(_discovery_checks(check))
    finally:
        set_current_tenant(None)

    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
