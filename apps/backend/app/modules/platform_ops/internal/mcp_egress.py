"""Política de egress para discovery de endpoint MCP direto."""

from __future__ import annotations

import ipaddress
import re
import socket
import threading
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from urllib.parse import urlsplit
from uuid import uuid4

from app.modules.platform_ops.internal.mcp_discovery import discover_endpoint_source
from app.modules.platform_ops.internal.mcp_endpoints import (
    EndpointStore,
    get_endpoint_record,
)
from app.modules.platform_ops.internal.mcp_endpoints import (
    endpoint_store as get_endpoint_store,
)
from app.modules.platform_ops.internal.mcp_endpoints import (
    validate_mcp_origin as validate_origin_structure,
)
from app.modules.platform_ops.internal.mcp_registry import (
    enabled_servers,
    server_for_kind,
)
from app.modules.tenancy.public import current_tenant_id


class EgressDenied(ValueError):
    """A origem não pode receber conexão de discovery."""


class DiscoveryBusy(RuntimeError):
    """Já existe uma discovery ativa para tenant e source."""


class DiscoveryLeaseStore(Protocol):
    def acquire(self, tenant_key: str, source_id: str, ttl_seconds: int) -> str: ...
    def release(self, tenant_key: str, source_id: str, lease_id: str) -> None: ...


class InMemoryDiscoveryLeaseStore:
    """Lease atômico de processo para dev/CI."""

    def __init__(self, *, clock: Callable[[], float] = time.monotonic) -> None:
        self._clock = clock
        self._expires: dict[tuple[str, str], float] = {}
        self._lock = threading.Lock()

    def acquire(self, tenant_key: str, source_id: str, ttl_seconds: int) -> str:
        key = (tenant_key, source_id)
        now = self._clock()
        with self._lock:
            if self._expires.get(key, 0) > now:
                raise DiscoveryBusy("MCP_DISCOVERY_BUSY")
            self._expires[key] = now + ttl_seconds
        return source_id

    def release(self, tenant_key: str, source_id: str, lease_id: str = "") -> None:
        del lease_id
        with self._lock:
            self._expires.pop((tenant_key, source_id), None)


class TableDiscoveryLeaseStore:
    """Lease distribuído com create/CAS na tabela do control plane."""

    def __init__(self, account_url: str, table_name: str, credential: Any) -> None:
        from azure.data.tables import TableServiceClient

        service = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = service.create_table_if_not_exists(table_name)

    def acquire(self, tenant_key: str, source_id: str, ttl_seconds: int) -> str:
        from azure.core import MatchConditions
        from azure.core.exceptions import HttpResponseError, ResourceExistsError

        lease_id = uuid4().hex
        expires_at = datetime.now(UTC) + timedelta(seconds=ttl_seconds)
        entity = {
            "PartitionKey": tenant_key,
            "RowKey": source_id,
            "leaseId": lease_id,
            "expiresAt": expires_at.isoformat(),
        }
        try:
            self._table.create_entity(entity)
            return lease_id
        except ResourceExistsError:
            current = self._table.get_entity(partition_key=tenant_key, row_key=source_id)
            if datetime.fromisoformat(current["expiresAt"]) > datetime.now(UTC):
                raise DiscoveryBusy("MCP_DISCOVERY_BUSY") from None
            try:
                self._table.update_entity(
                    entity,
                    etag=current.metadata["etag"],
                    match_condition=MatchConditions.IfNotModified,
                )
            except HttpResponseError as exc:
                raise DiscoveryBusy("MCP_DISCOVERY_BUSY") from exc
            return lease_id

    def release(self, tenant_key: str, source_id: str, lease_id: str) -> None:
        from azure.core import MatchConditions
        from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

        try:
            current = self._table.get_entity(partition_key=tenant_key, row_key=source_id)
            if current.get("leaseId") != lease_id:
                return
            self._table.delete_entity(
                partition_key=tenant_key,
                row_key=source_id,
                etag=current.metadata["etag"],
                match_condition=MatchConditions.IfNotModified,
            )
        except (HttpResponseError, ResourceNotFoundError):
            return


_memory_leases = InMemoryDiscoveryLeaseStore()
_configured_leases: DiscoveryLeaseStore | None = None


def discovery_lease_store() -> DiscoveryLeaseStore:
    global _configured_leases
    if _configured_leases is not None:
        return _configured_leases

    from app.shared.settings import settings

    if settings.deployment_mode != "shared" or settings.tenant_store_backend == "memory":
        return _memory_leases
    if not settings.tenant_store_account_url:
        raise RuntimeError("TENANT_STORE_ACCOUNT_URL is required for MCP discovery leases")

    from azure.identity import DefaultAzureCredential

    _configured_leases = TableDiscoveryLeaseStore(
        settings.tenant_store_account_url,
        "mcpDiscoveryLeases",
        DefaultAzureCredential(),
    )
    return _configured_leases


def _tenant_key() -> str:
    return current_tenant_id() or "self-hosted"


def _resolve(host: str, port: int) -> list[str]:
    try:
        answers = socket.getaddrinfo(host, port, type=socket.SOCK_STREAM)
    except socket.gaierror as exc:
        raise EgressDenied("MCP_DNS_REJECTED") from exc
    return sorted({answer[4][0] for answer in answers})


def _public(address: str) -> bool:
    try:
        parsed = ipaddress.ip_address(address)
    except ValueError:
        return False
    return parsed.is_global and not any(
        (
            parsed.is_private,
            parsed.is_loopback,
            parsed.is_link_local,
            parsed.is_multicast,
            parsed.is_reserved,
            parsed.is_unspecified,
        )
    )


def validate_mcp_origin(
    value: str,
    *,
    resolver: Callable[[str, int], list[str]] = _resolve,
    resolve: bool = False,
) -> str:
    try:
        origin = validate_origin_structure(value)
    except ValueError as exc:
        raise EgressDenied("MCP_EGRESS_DENIED") from exc
    if resolve:
        host = urlsplit(origin).hostname or ""
        addresses = resolver(host, 443)
        if not addresses or any(not _public(address) for address in addresses):
            raise EgressDenied("MCP_EGRESS_DENIED")
    return origin


def _matches_registered_origin(template: str, origin: str) -> bool:
    if "{org}" not in template:
        return template == origin
    pattern = re.escape(template).replace(re.escape("{org}"), r"[^/?#]+")
    return re.fullmatch(pattern, origin) is not None


def _cached_bearer_provider(resolver: Callable[[], str]):
    from azure.core.exceptions import AzureError

    from app.modules.foundry.public import ConnectionCredentialUnavailable

    bearer: str | None = None

    def provider(_headers: dict[str, Any]) -> dict[str, str]:
        nonlocal bearer
        if bearer is None:
            try:
                bearer = resolver()
            except (AzureError, ConnectionCredentialUnavailable):
                raise EgressDenied("MCP_AUTH_NOT_AVAILABLE") from None
            if not isinstance(bearer, str) or not bearer:
                raise EgressDenied("MCP_AUTH_NOT_AVAILABLE")
        return {"Authorization": f"Bearer {bearer}"}

    return provider


def _endpoint_header_provider(
    endpoint,
    *,
    connection_lookup,
    connection_credential_resolver,
    request_credential,
):
    if endpoint.auth_mode == "public":
        return None
    if endpoint.auth_mode == "connection":
        connection = connection_lookup(endpoint.connection_ref)
        server = server_for_kind(connection.kind) if connection is not None else None
        if (
            connection is None
            or not connection.enabled
            or not connection.foundry_connection_id
            or server is None
            or server.auth not in {"github_pat", "oauth_passthrough"}
            or not _matches_registered_origin(server.url, endpoint.origin)
        ):
            raise EgressDenied("MCP_AUTH_NOT_AVAILABLE")
        return _cached_bearer_provider(
            lambda: connection_credential_resolver(
                connection.foundry_connection_id, endpoint.origin
            )
        )
    if endpoint.auth_mode == "obo":
        server = next(
            (
                candidate
                for candidate in enabled_servers()
                if candidate.auth == "obo"
                and candidate.obo_scope
                and _matches_registered_origin(candidate.url, endpoint.origin)
            ),
            None,
        )
        if server is None:
            raise EgressDenied("MCP_AUTH_NOT_AVAILABLE")
        return _cached_bearer_provider(
            lambda: request_credential().get_token(server.obo_scope).token
        )
    raise EgressDenied("MCP_AUTH_NOT_AVAILABLE")


async def discover_endpoint(
    endpoint_id: str,
    *,
    endpoint_store: EndpointStore | None = None,
    lease_store: DiscoveryLeaseStore | None = None,
    resolver: Callable[[str, int], list[str]] = _resolve,
    discovery: Callable[..., Any] = discover_endpoint_source,
    evidence_store=None,
    connection_lookup=None,
    connection_credential_resolver=None,
    request_credential=None,
) -> dict:
    target_store = endpoint_store or get_endpoint_store()
    endpoint = get_endpoint_record(endpoint_id, store=target_store)
    if endpoint is None:
        raise EgressDenied("MCP_SOURCE_NOT_FOUND")
    if endpoint.status != "approved":
        raise EgressDenied("MCP_ENDPOINT_NOT_APPROVED")

    if connection_lookup is None:
        from app.modules.tenancy.public import current_connection

        connection_lookup = current_connection
    if connection_credential_resolver is None:
        from app.modules.foundry.public import resolve_connection_bearer

        connection_credential_resolver = resolve_connection_bearer
    if request_credential is None:
        from app.shared.auth import credential_for_request

        request_credential = credential_for_request
    header_provider = _endpoint_header_provider(
        endpoint,
        connection_lookup=connection_lookup,
        connection_credential_resolver=connection_credential_resolver,
        request_credential=request_credential,
    )

    tenant_key = _tenant_key()
    target_leases = lease_store or discovery_lease_store()
    lease_id = target_leases.acquire(tenant_key, endpoint.id, ttl_seconds=30)
    try:
        origin = validate_mcp_origin(endpoint.origin, resolver=resolver, resolve=True)
        return await discovery(
            {"kind": "endpoint", "id": endpoint.id, "url": origin},
            follow_redirects=False,
            header_provider=header_provider,
            evidence_store=evidence_store,
        )
    finally:
        target_leases.release(tenant_key, endpoint.id, lease_id)
