"""F04: discovery autentica tarde e somente contra a origem tenant-local aprovada."""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from app.modules.platform_ops.public import (
    EgressDenied,
    InMemoryDiscoveryLeaseStore,
    InMemoryEndpointStore,
    approve_mcp_endpoint,
    create_mcp_endpoint,
    discover_endpoint,
)
from app.modules.tenancy.public import Connection, set_current_tenant


def _approved(store, origin: str, auth: dict) -> dict:
    endpoint = create_mcp_endpoint({"url": origin, "auth": auth}, store=store)
    return approve_mcp_endpoint(
        endpoint["id"],
        decision="approved",
        reason="teste F04",
        store=store,
        audit_recorder=lambda **_event: {"hash": "audit"},
        actor="human:admin",
    )


async def _checks(check) -> None:
    dns = lambda _host, _port: ["20.42.1.10"]

    public_store = InMemoryEndpointStore()
    public = _approved(
        public_store, "https://public.example.test/mcp", {"mode": "public"}
    )
    public_calls: list[dict] = []

    async def capture_public(source, **kwargs):
        public_calls.append({"source": source, **kwargs})
        return {"snapshotId": "public"}

    await discover_endpoint(
        public["id"],
        endpoint_store=public_store,
        lease_store=InMemoryDiscoveryLeaseStore(),
        resolver=dns,
        discovery=capture_public,
    )
    check("public não envia header provider", public_calls[0]["header_provider"] is None)

    connection_store = InMemoryEndpointStore()
    connection = _approved(
        connection_store,
        "https://api.githubcopilot.com/mcp/",
        {"mode": "connection", "connectionRef": "github-main"},
    )
    resolved: list[str] = []
    brokered: list[tuple[str, str]] = []

    def lookup(connection_id: str):
        resolved.append(connection_id)
        return Connection(
            id="github-main",
            kind="github",
            label="GitHub",
            foundry_connection_id="foundry-github",
        )

    def broker(connection_id: str, expected_origin: str) -> str:
        brokered.append((connection_id, expected_origin))
        return "runtime-canary"

    async def invoke_provider(_source, **kwargs):
        check("credencial não é resolvida antes da sessão", brokered == [])
        provider = kwargs["header_provider"]
        first = provider({})
        second = provider({})
        check("connection usa bearer", first == {"Authorization": "Bearer runtime-canary"})
        check("credencial é resolvida uma vez por sessão", first == second and len(brokered) == 1)
        return {"snapshotId": "connection"}

    await discover_endpoint(
        connection["id"],
        endpoint_store=connection_store,
        lease_store=InMemoryDiscoveryLeaseStore(),
        resolver=dns,
        discovery=invoke_provider,
        connection_lookup=lookup,
        connection_credential_resolver=broker,
    )
    check("connectionRef é resolvida no tenant", resolved == ["github-main"])
    check(
        "broker recebe apenas referência Foundry e origin aprovada",
        brokered == [("foundry-github", "https://api.githubcopilot.com/mcp/")],
    )

    for name, bad_connection in (
        ("connection ausente", None),
        (
            "connection desabilitada",
            Connection(id="github-main", kind="github", label="GitHub", enabled=False),
        ),
        (
            "auth incompatível",
            Connection(id="github-main", kind="learn", label="Learn"),
        ),
    ):
        discovery_called = False

        async def must_not_discover(_source, **_kwargs):
            nonlocal discovery_called
            discovery_called = True
            return {}

        try:
            await discover_endpoint(
                connection["id"],
                endpoint_store=connection_store,
                lease_store=InMemoryDiscoveryLeaseStore(),
                resolver=dns,
                discovery=must_not_discover,
                connection_lookup=lambda _id, value=bad_connection: value,
                connection_credential_resolver=broker,
            )
        except EgressDenied as exc:
            check(name, str(exc) == "MCP_AUTH_NOT_AVAILABLE" and not discovery_called)
        else:
            check(name, False)

    obo_store = InMemoryEndpointStore()
    obo = _approved(
        obo_store,
        "https://mcp.dev.azure.com/contoso",
        {"mode": "obo"},
    )
    scopes: list[str] = []

    class Credential:
        def get_token(self, scope: str):
            scopes.append(scope)
            return SimpleNamespace(token="obo-canary")

    async def invoke_obo(_source, **kwargs):
        check("OBO não é resolvido antes da sessão", scopes == [])
        headers = kwargs["header_provider"]({})
        check("OBO usa bearer", headers == {"Authorization": "Bearer obo-canary"})
        return {"snapshotId": "obo"}

    await discover_endpoint(
        obo["id"],
        endpoint_store=obo_store,
        lease_store=InMemoryDiscoveryLeaseStore(),
        resolver=dns,
        discovery=invoke_obo,
        request_credential=lambda: Credential(),
    )
    check(
        "audience OBO vem da allowlist",
        scopes == ["499b84ac-1321-427f-aa17-267ca6975798/.default"],
    )


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    set_current_tenant(SimpleNamespace(tid="tenant-a"))
    try:
        asyncio.run(_checks(check))
    finally:
        set_current_tenant(None)
    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
