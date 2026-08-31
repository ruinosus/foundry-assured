"""Registro tenant-scoped de endpoints MCP aprovados para discovery."""

from __future__ import annotations

import ipaddress
import json
import re
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol
from urllib.parse import urlsplit, urlunsplit
from uuid import uuid4

from app.modules.audit.public import actor as current_actor
from app.modules.audit.public import record
from app.modules.tenancy.public import current_tenant_id

_DNS_NAME = re.compile(
    r"^(?=.{1,253}\.?$)(?:[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.)*"
    r"[A-Za-z0-9](?:[A-Za-z0-9-]{0,61}[A-Za-z0-9])?\.?$"
)
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class EndpointInvalid(ValueError):
    """A proposta de endpoint não satisfaz o contrato inerte."""


class EndpointConflict(RuntimeError):
    """A decisão ou revisão conflita com o estado persistido."""


@dataclass(frozen=True)
class McpEndpoint:
    id: str
    tenant_key: str
    origin: str
    auth_mode: str
    connection_ref: str | None
    status: str
    created_at: str
    created_by: str
    decision_at: str | None = None
    decision_by: str | None = None
    decision_reason: str | None = None
    revision: int = 1


class EndpointStore(Protocol):
    def get(self, tenant_key: str, endpoint_id: str) -> McpEndpoint | None: ...
    def list(self, tenant_key: str) -> list[McpEndpoint]: ...
    def create(self, endpoint: McpEndpoint) -> None: ...
    def replace(self, endpoint: McpEndpoint, expected_revision: int) -> None: ...


class InMemoryEndpointStore:
    """Fake offline com o mesmo isolamento e CAS do adapter Azure Table."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], McpEndpoint] = {}

    def get(self, tenant_key: str, endpoint_id: str) -> McpEndpoint | None:
        return self._records.get((tenant_key, endpoint_id))

    def list(self, tenant_key: str) -> list[McpEndpoint]:
        return sorted(
            (item for (tenant, _), item in self._records.items() if tenant == tenant_key),
            key=lambda item: item.created_at,
        )

    def create(self, endpoint: McpEndpoint) -> None:
        key = (endpoint.tenant_key, endpoint.id)
        if key in self._records:
            raise EndpointConflict("MCP_ENDPOINT_EXISTS")
        self._records[key] = endpoint

    def replace(self, endpoint: McpEndpoint, expected_revision: int) -> None:
        current = self.get(endpoint.tenant_key, endpoint.id)
        if current is None or current.revision != expected_revision:
            raise EndpointConflict("MCP_ENDPOINT_REVISION_CONFLICT")
        self._records[(endpoint.tenant_key, endpoint.id)] = endpoint


class TableEndpointStore:
    """Azure Table keyless; PartitionKey=tenant e RowKey=endpoint id."""

    def __init__(self, account_url: str, table_name: str, credential: Any) -> None:
        from azure.data.tables import TableServiceClient

        service = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = service.create_table_if_not_exists(table_name)

    @staticmethod
    def _from_entity(entity: dict[str, Any]) -> McpEndpoint:
        payload = json.loads(entity["payload"])
        return McpEndpoint(**payload)

    @staticmethod
    def _entity(endpoint: McpEndpoint) -> dict[str, Any]:
        return {
            "PartitionKey": endpoint.tenant_key,
            "RowKey": endpoint.id,
            "payload": json.dumps(asdict(endpoint), separators=(",", ":")),
            "revision": endpoint.revision,
        }

    def get(self, tenant_key: str, endpoint_id: str) -> McpEndpoint | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            entity = self._table.get_entity(partition_key=tenant_key, row_key=endpoint_id)
        except ResourceNotFoundError:
            return None
        return self._from_entity(entity)

    def list(self, tenant_key: str) -> list[McpEndpoint]:
        escaped = tenant_key.replace("'", "''")
        return [
            self._from_entity(entity)
            for entity in self._table.query_entities(f"PartitionKey eq '{escaped}'")
        ]

    def create(self, endpoint: McpEndpoint) -> None:
        from azure.core.exceptions import ResourceExistsError

        try:
            self._table.create_entity(self._entity(endpoint))
        except ResourceExistsError as exc:
            raise EndpointConflict("MCP_ENDPOINT_EXISTS") from exc

    def replace(self, endpoint: McpEndpoint, expected_revision: int) -> None:
        from azure.core import MatchConditions
        from azure.core.exceptions import HttpResponseError, ResourceNotFoundError

        try:
            current = self._table.get_entity(
                partition_key=endpoint.tenant_key, row_key=endpoint.id
            )
            if int(current.get("revision", 0)) != expected_revision:
                raise EndpointConflict("MCP_ENDPOINT_REVISION_CONFLICT")
            self._table.update_entity(
                self._entity(endpoint),
                etag=current.metadata["etag"],
                match_condition=MatchConditions.IfNotModified,
            )
        except (HttpResponseError, ResourceNotFoundError) as exc:
            raise EndpointConflict("MCP_ENDPOINT_REVISION_CONFLICT") from exc


_memory_store = InMemoryEndpointStore()
_configured_store: EndpointStore | None = None


def endpoint_store() -> EndpointStore:
    global _configured_store
    if _configured_store is not None:
        return _configured_store

    from app.shared.settings import settings

    if settings.deployment_mode != "shared" or settings.tenant_store_backend == "memory":
        return _memory_store
    if not settings.tenant_store_account_url:
        raise RuntimeError("TENANT_STORE_ACCOUNT_URL is required for MCP endpoint storage")

    from azure.identity import DefaultAzureCredential

    _configured_store = TableEndpointStore(
        settings.tenant_store_account_url,
        "mcpEndpoints",
        DefaultAzureCredential(),
    )
    return _configured_store


def _tenant_key() -> str:
    return current_tenant_id() or "self-hosted"


def validate_mcp_origin(value: str) -> str:
    if not isinstance(value, str) or len(value) > 2048:
        raise EndpointInvalid("MCP_ENDPOINT_INVALID")
    try:
        parsed = urlsplit(value)
        port = parsed.port
    except ValueError as exc:
        raise EndpointInvalid("MCP_ENDPOINT_INVALID") from exc
    host = parsed.hostname or ""
    try:
        ipaddress.ip_address(host)
    except ValueError:
        pass
    else:
        raise EndpointInvalid("MCP_ENDPOINT_INVALID")
    if (
        parsed.scheme.lower() != "https"
        or parsed.username is not None
        or parsed.password is not None
        or port not in (None, 443)
        or parsed.query
        or parsed.fragment
        or not host
        or not _DNS_NAME.fullmatch(host)
    ):
        raise EndpointInvalid("MCP_ENDPOINT_INVALID")
    path = parsed.path or ""
    if "//" in path or "\\" in path or any(ord(char) < 32 for char in path):
        raise EndpointInvalid("MCP_ENDPOINT_INVALID")
    return urlunsplit(("https", host.lower(), path, "", ""))


def _auth(value: Any) -> tuple[str, str | None]:
    if not isinstance(value, dict) or set(value) - {"mode", "connectionRef"}:
        raise EndpointInvalid("MCP_ENDPOINT_AUTH_INVALID")
    mode = value.get("mode")
    reference = value.get("connectionRef")
    if mode not in {"public", "connection", "obo"}:
        raise EndpointInvalid("MCP_ENDPOINT_AUTH_INVALID")
    if mode == "connection":
        if not isinstance(reference, str) or not _REFERENCE.fullmatch(reference):
            raise EndpointInvalid("MCP_ENDPOINT_AUTH_INVALID")
    elif reference is not None:
        raise EndpointInvalid("MCP_ENDPOINT_AUTH_INVALID")
    return mode, reference


def _projection(endpoint: McpEndpoint) -> dict[str, Any]:
    result: dict[str, Any] = {
        "id": endpoint.id,
        "origin": endpoint.origin,
        "auth": {"mode": endpoint.auth_mode},
        "status": endpoint.status,
        "createdAt": endpoint.created_at,
        "createdBy": endpoint.created_by,
        "revision": endpoint.revision,
    }
    if endpoint.connection_ref:
        result["auth"]["connectionRef"] = endpoint.connection_ref
    if endpoint.decision_at:
        result.update(
            {
                "decisionAt": endpoint.decision_at,
                "decisionBy": endpoint.decision_by,
                "decisionReason": endpoint.decision_reason,
            }
        )
    return result


def create_mcp_endpoint(
    proposal: dict[str, Any],
    *,
    store: EndpointStore | None = None,
    network_probe=None,
    actor: str | None = None,
) -> dict[str, Any]:
    del network_probe
    if not isinstance(proposal, dict) or set(proposal) != {"url", "auth"}:
        raise EndpointInvalid("MCP_ENDPOINT_INVALID")
    origin = validate_mcp_origin(proposal["url"])
    auth_mode, connection_ref = _auth(proposal["auth"])
    endpoint = McpEndpoint(
        id=f"mep_{uuid4().hex}",
        tenant_key=_tenant_key(),
        origin=origin,
        auth_mode=auth_mode,
        connection_ref=connection_ref,
        status="pending",
        created_at=datetime.now(UTC).isoformat(timespec="seconds"),
        created_by=actor or current_actor(),
    )
    (store or endpoint_store()).create(endpoint)
    return _projection(endpoint)


def get_endpoint_record(
    endpoint_id: str, *, store: EndpointStore | None = None
) -> McpEndpoint | None:
    return (store or endpoint_store()).get(_tenant_key(), endpoint_id)


def get_mcp_endpoint(endpoint_id: str, *, store: EndpointStore | None = None) -> dict | None:
    endpoint = get_endpoint_record(endpoint_id, store=store)
    return _projection(endpoint) if endpoint else None


def resolve_approved_endpoint(
    endpoint_id: str, *, store: EndpointStore | None = None
) -> dict[str, Any] | None:
    endpoint = get_endpoint_record(endpoint_id, store=store)
    if endpoint is None or endpoint.status != "approved":
        return None
    return {"kind": "endpoint", "id": endpoint.id}


def list_mcp_endpoints(*, store: EndpointStore | None = None) -> list[dict]:
    return [_projection(item) for item in (store or endpoint_store()).list(_tenant_key())]


def approve_mcp_endpoint(
    endpoint_id: str,
    *,
    decision: str,
    reason: str,
    store: EndpointStore | None = None,
    audit_recorder=record,
    actor: str | None = None,
) -> dict:
    target_store = store or endpoint_store()
    endpoint = target_store.get(_tenant_key(), endpoint_id)
    if endpoint is None:
        raise LookupError("MCP_SOURCE_NOT_FOUND")
    if endpoint.status != "pending":
        raise EndpointConflict("MCP_ENDPOINT_ALREADY_DECIDED")
    if decision not in {"approved", "rejected"} or not isinstance(reason, str):
        raise EndpointInvalid("MCP_ENDPOINT_DECISION_INVALID")
    reason = reason.strip()
    if not reason or len(reason) > 500:
        raise EndpointInvalid("MCP_ENDPOINT_DECISION_INVALID")
    decided_by = actor or current_actor()
    decided = replace(
        endpoint,
        status=decision,
        decision_at=datetime.now(UTC).isoformat(timespec="seconds"),
        decision_by=decided_by,
        decision_reason=reason,
        revision=endpoint.revision + 1,
    )
    audit_recorder(
        scope=_tenant_key(),
        actor=decided_by,
        kind="approval",
        summary=f"Endpoint MCP {decision}",
        ref=endpoint.id,
        detail={"decision": decision, "revision": decided.revision},
    )
    target_store.replace(decided, expected_revision=endpoint.revision)
    return _projection(decided)
