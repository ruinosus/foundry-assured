"""Registry bindings operacionais, escopados por tenant e área.

O registro persiste somente referências já validadas. Descoberta, classificação e decisão de
conformidade continuam nos componentes MCP donos; este módulo apenas compõe seus resultados.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

from app.modules.audit.public import record as record_audit
from app.modules.okf.public import AuthoringInvalid, parse_mcp_binding
from app.modules.platform_ops.internal.mcp_conformity import evaluate_mcp_binding

_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,62}$")
_REFERENCE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._:-]{0,127}$")


class RegistryBindingInvalid(ValueError):
    """A configuração contém referência inválida ou fora do escopo."""


class RegistryBindingConflict(RuntimeError):
    """A revisão mudou desde a leitura do Admin."""


@dataclass(frozen=True)
class RegistryBindingScope:
    tenant_id: str
    area_id: str

    @property
    def key(self) -> str:
        return f"{self.tenant_id}:{self.area_id}"


@dataclass(frozen=True)
class RegistryBindingRecord:
    id: str
    scope_key: str
    name: str
    connection_id: str
    risk: str
    binding: dict[str, Any]
    source: dict[str, Any]
    snapshot: dict[str, Any]
    tools: tuple[dict[str, Any], ...]
    status: str
    reasons: tuple[str, ...]
    revision: int
    updated_at: str
    updated_by: str


class RegistryBindingStore(Protocol):
    def get(self, scope_key: str, binding_id: str) -> RegistryBindingRecord | None: ...
    def list(self, scope_key: str) -> list[RegistryBindingRecord]: ...
    def replace(self, record: RegistryBindingRecord, expected_revision: int) -> None: ...


class InMemoryRegistryBindingStore:
    def __init__(self) -> None:
        self._records: dict[tuple[str, str], RegistryBindingRecord] = {}

    def get(self, scope_key: str, binding_id: str) -> RegistryBindingRecord | None:
        return self._records.get((scope_key, binding_id))

    def list(self, scope_key: str) -> list[RegistryBindingRecord]:
        return sorted(
            (
                record
                for (record_scope, _), record in self._records.items()
                if record_scope == scope_key
            ),
            key=lambda record: record.name.casefold(),
        )

    def replace(self, record: RegistryBindingRecord, expected_revision: int) -> None:
        key = (record.scope_key, record.id)
        current = self._records.get(key)
        current_revision = current.revision if current else 0
        if current_revision != expected_revision:
            raise RegistryBindingConflict("REGISTRY_BINDING_REVISION_CONFLICT")
        self._records[key] = record


class TableRegistryBindingStore:
    """Azure Table keyless; partição é o escopo tenant-área e linha é o binding."""

    def __init__(self, account_url: str, table_name: str, credential: Any) -> None:
        from azure.data.tables import TableServiceClient

        service = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = service.create_table_if_not_exists(table_name)

    @staticmethod
    def _from_entity(entity: dict[str, Any]) -> RegistryBindingRecord:
        payload = json.loads(entity["payload"])
        payload["tools"] = tuple(payload.get("tools") or ())
        payload["reasons"] = tuple(payload.get("reasons") or ())
        return RegistryBindingRecord(**payload)

    @staticmethod
    def _entity(record: RegistryBindingRecord) -> dict[str, Any]:
        return {
            "PartitionKey": record.scope_key,
            "RowKey": record.id,
            "payload": json.dumps(asdict(record), separators=(",", ":")),
            "status": record.status,
            "revision": record.revision,
        }

    def get(self, scope_key: str, binding_id: str) -> RegistryBindingRecord | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            entity = self._table.get_entity(
                partition_key=scope_key, row_key=binding_id
            )
        except ResourceNotFoundError:
            return None
        return self._from_entity(entity)

    def list(self, scope_key: str) -> list[RegistryBindingRecord]:
        escaped = scope_key.replace("'", "''")
        return sorted(
            (
                self._from_entity(entity)
                for entity in self._table.query_entities(
                    f"PartitionKey eq '{escaped}'"
                )
            ),
            key=lambda record: record.name.casefold(),
        )

    def replace(self, record: RegistryBindingRecord, expected_revision: int) -> None:
        from azure.core import MatchConditions
        from azure.core.exceptions import (
            HttpResponseError,
            ResourceExistsError,
            ResourceNotFoundError,
        )

        entity = self._entity(record)
        try:
            if expected_revision == 0:
                self._table.create_entity(entity)
                return
            current = self._table.get_entity(
                partition_key=record.scope_key, row_key=record.id
            )
            if int(current.get("revision", 0)) != expected_revision:
                raise RegistryBindingConflict("REGISTRY_BINDING_REVISION_CONFLICT")
            self._table.update_entity(
                entity,
                etag=current.metadata["etag"],
                match_condition=MatchConditions.IfNotModified,
            )
        except (HttpResponseError, ResourceExistsError, ResourceNotFoundError) as exc:
            raise RegistryBindingConflict("REGISTRY_BINDING_REVISION_CONFLICT") from exc


def _projection(record: RegistryBindingRecord) -> dict[str, Any]:
    return {
        "id": record.id,
        "name": record.name,
        "connectionId": record.connection_id,
        "risk": record.risk,
        "binding": record.binding,
        "source": record.source,
        "snapshot": record.snapshot,
        "tools": list(record.tools),
        "status": record.status,
        "reasons": list(record.reasons),
        "revision": record.revision,
        "updatedAt": record.updated_at,
        "updatedBy": record.updated_by,
    }


class RegistryBindingService:
    def __init__(
        self,
        store: RegistryBindingStore,
        *,
        connection_exists: Callable[[str, str], bool],
        conformity_evaluator: Callable[[dict[str, Any]], dict[str, Any]] = evaluate_mcp_binding,
        audit_recorder: Callable[..., Any] = record_audit,
    ) -> None:
        self._store = store
        self._connection_exists = connection_exists
        self._evaluate = conformity_evaluator
        self._audit = audit_recorder

    @staticmethod
    def _proposal(value: dict[str, Any]) -> tuple[str, str, str, str, dict[str, Any], int | None]:
        allowed = {"id", "name", "connectionId", "risk", "binding", "expectedRevision"}
        if not isinstance(value, dict) or set(value) - allowed:
            raise RegistryBindingInvalid("REGISTRY_BINDING_INVALID")
        binding_id = value.get("id")
        name = value.get("name")
        connection_id = value.get("connectionId")
        risk = value.get("risk")
        binding = value.get("binding")
        expected = value.get("expectedRevision")
        if (
            not isinstance(binding_id, str)
            or not _ID.fullmatch(binding_id)
            or not isinstance(name, str)
            or not name.strip()
            or len(name.strip()) > 120
            or not isinstance(connection_id, str)
            or not _REFERENCE.fullmatch(connection_id)
            or risk not in {"read", "write"}
            or not isinstance(binding, dict)
            or (expected is not None and (not isinstance(expected, int) or expected < 1))
        ):
            raise RegistryBindingInvalid("REGISTRY_BINDING_INVALID")
        try:
            parse_mcp_binding(binding)
        except AuthoringInvalid as exc:
            raise RegistryBindingInvalid(str(exc)) from exc
        return binding_id, name.strip(), connection_id, risk, binding, expected

    def put(
        self, scope: RegistryBindingScope, proposal: dict[str, Any], *, actor: str
    ) -> dict[str, Any]:
        binding_id, name, connection_id, risk, binding, expected = self._proposal(
            proposal
        )
        if not self._connection_exists(scope.tenant_id, connection_id):
            raise RegistryBindingInvalid("REGISTRY_CONNECTION_NOT_FOUND")
        current = self._store.get(scope.key, binding_id)
        current_revision = current.revision if current else 0
        if (current is None and expected is not None) or (
            current is not None and expected != current.revision
        ):
            raise RegistryBindingConflict("REGISTRY_BINDING_REVISION_CONFLICT")
        conformity = self._evaluate(binding)
        blocked = conformity.get("status") != "pass"
        record = RegistryBindingRecord(
            id=binding_id,
            scope_key=scope.key,
            name=name,
            connection_id=connection_id,
            risk=risk,
            binding=dict(binding),
            source=dict(conformity.get("source") or {}),
            snapshot=dict(conformity.get("snapshot") or {}),
            tools=tuple(dict(item) for item in conformity.get("tools") or ()),
            status="blocked" if blocked else "pending_review",
            reasons=tuple(str(reason) for reason in conformity.get("reasons") or ()),
            revision=current_revision + 1,
            updated_at=datetime.now(UTC).isoformat(timespec="seconds"),
            updated_by=actor,
        )
        self._audit(
            scope=scope.key,
            actor=actor,
            kind="write",
            summary="Registry binding validado para persistência",
            ref=binding_id,
            detail={
                "connectionId": connection_id,
                "risk": risk,
                "status": record.status,
                "revision": record.revision,
                "reasonCodes": list(record.reasons),
            },
        )
        self._store.replace(record, current_revision)
        return _projection(record)

    def list(self, scope: RegistryBindingScope) -> dict[str, Any]:
        return {"items": [_projection(record) for record in self._store.list(scope.key)]}

    def get(self, scope: RegistryBindingScope, binding_id: str) -> dict[str, Any] | None:
        record = self._store.get(scope.key, binding_id)
        return _projection(record) if record else None

    def refresh(
        self, scope: RegistryBindingScope, binding_id: str, *, actor: str
    ) -> dict[str, Any]:
        current = self._store.get(scope.key, binding_id)
        if current is None:
            raise RegistryBindingInvalid("REGISTRY_BINDING_NOT_FOUND")
        return self.put(
            scope,
            {
                "id": current.id,
                "name": current.name,
                "connectionId": current.connection_id,
                "risk": current.risk,
                "binding": current.binding,
                "expectedRevision": current.revision,
            },
            actor=actor,
        )


_memory_store = InMemoryRegistryBindingStore()
_configured_store: RegistryBindingStore | None = None


def registry_binding_store() -> RegistryBindingStore:
    global _configured_store
    if _configured_store is not None:
        return _configured_store

    from app.shared.settings import settings

    if settings.deployment_mode != "shared" or settings.tenant_store_backend == "memory":
        return _memory_store
    if not settings.tenant_store_account_url:
        raise RuntimeError("TENANT_STORE_ACCOUNT_URL is required for registry bindings")

    from azure.identity import DefaultAzureCredential

    _configured_store = TableRegistryBindingStore(
        settings.tenant_store_account_url,
        "registryBindings",
        DefaultAzureCredential(),
    )
    return _configured_store
