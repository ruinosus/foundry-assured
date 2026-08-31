"""F04: segredo de autenticação não aparece em saídas ou evidências de discovery."""

from __future__ import annotations

import asyncio
import json
import sys
from types import SimpleNamespace

from app.modules.foundry.public import ConnectionCredentialUnavailable
from app.modules.platform_ops.public import (
    EgressDenied,
    InMemoryDiscoveryLeaseStore,
    InMemoryEndpointStore,
    approve_mcp_endpoint,
    create_mcp_endpoint,
    discover_endpoint,
)
from app.modules.tenancy.public import Connection, set_current_tenant


async def _run() -> tuple[dict, list[dict], list[str]]:
    secret = "F04-CANARY-DO-NOT-PERSIST"
    store = InMemoryEndpointStore()
    endpoint = create_mcp_endpoint(
        {
            "url": "https://api.githubcopilot.com/mcp/",
            "auth": {"mode": "connection", "connectionRef": "github-main"},
        },
        store=store,
    )
    endpoint = approve_mcp_endpoint(
        endpoint["id"],
        decision="approved",
        reason="teste canário",
        store=store,
        audit_recorder=lambda **_event: {"hash": "audit"},
        actor="human:admin",
    )
    durable_writes: list[dict] = []
    observed_headers: list[str] = []

    async def discovery(source, **kwargs):
        headers = kwargs["header_provider"]({})
        observed_headers.append(headers["Authorization"])
        snapshot = {
            "snapshotId": "msnap_canary",
            "source": {"kind": source["kind"], "id": source["id"]},
            "tools": [],
        }
        durable_writes.append(snapshot)
        return snapshot

    result = await discover_endpoint(
        endpoint["id"],
        endpoint_store=store,
        lease_store=InMemoryDiscoveryLeaseStore(),
        resolver=lambda _host, _port: ["20.42.1.10"],
        discovery=discovery,
        connection_lookup=lambda _id: Connection(
            id="github-main",
            kind="github",
            label="GitHub",
            foundry_connection_id="foundry-github",
        ),
        connection_credential_resolver=lambda _id, _origin: secret,
    )
    return result, durable_writes, observed_headers


async def _failed_auth_message(secret: str) -> str:
    store = InMemoryEndpointStore()
    endpoint = create_mcp_endpoint(
        {
            "url": "https://api.githubcopilot.com/mcp/",
            "auth": {"mode": "connection", "connectionRef": "github-main"},
        },
        store=store,
    )
    endpoint = approve_mcp_endpoint(
        endpoint["id"],
        decision="approved",
        reason="teste erro",
        store=store,
        audit_recorder=lambda **_event: {"hash": "audit"},
        actor="human:admin",
    )

    async def discovery(_source, **kwargs):
        kwargs["header_provider"]({})
        return {}

    try:
        await discover_endpoint(
            endpoint["id"],
            endpoint_store=store,
            lease_store=InMemoryDiscoveryLeaseStore(),
            resolver=lambda _host, _port: ["20.42.1.10"],
            discovery=discovery,
            connection_lookup=lambda _id: Connection(
                id="github-main",
                kind="github",
                label="GitHub",
                foundry_connection_id="foundry-github",
            ),
            connection_credential_resolver=lambda _id, _origin: (_ for _ in ()).throw(
                ConnectionCredentialUnavailable(secret)
            ),
        )
    except EgressDenied as exc:
        return str(exc)
    return ""


def main() -> int:
    secret = "F04-CANARY-DO-NOT-PERSIST"
    set_current_tenant(SimpleNamespace(tid="tenant-a"))
    try:
        result, durable_writes, observed_headers = asyncio.run(_run())
        failed_auth = asyncio.run(_failed_auth_message(secret))
    finally:
        set_current_tenant(None)

    serialized = json.dumps({"response": result, "writes": durable_writes}, default=str)
    checks = {
        "canário chegou somente ao header efêmero": observed_headers == [f"Bearer {secret}"],
        "canário ausente da response e storage": secret not in serialized,
        "Authorization ausente da response e storage": "Authorization" not in serialized,
        "erro de auth é genérico": failed_auth == "MCP_AUTH_NOT_AVAILABLE",
    }
    failures = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
