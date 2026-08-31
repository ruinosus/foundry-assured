"""Classificação administrativa tenant-scoped para contratos de tools MCP."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from typing import Any, Protocol

import rfc8785

from app.modules.audit.public import actor as current_actor
from app.modules.audit.public import read_evidence, record
from app.modules.tenancy.public import current_tenant_id


class ClassificationInvalid(ValueError):
    """A decisão não satisfaz o contrato administrativo."""


class ClassificationConflict(RuntimeError):
    """A revisão esperada não corresponde à decisão atual."""


class ClassificationNotFound(LookupError):
    """O snapshot ou a tool não existe no tenant atual."""


@dataclass(frozen=True)
class McpToolClassification:
    tenant_key: str
    source_id: str
    tool_name: str
    contract_hash: str
    effect: str
    reason: str
    revision: int
    decided_at: str
    decided_by: str


class ClassificationStore(Protocol):
    def get(
        self, tenant_key: str, source_id: str, tool_name: str, contract_hash: str
    ) -> McpToolClassification | None: ...

    def replace(
        self, decision: McpToolClassification, expected_revision: int
    ) -> None: ...


def _row_key(source_id: str, tool_name: str, contract_hash: str) -> str:
    return hashlib.sha256(
        rfc8785.dumps(
            {
                "sourceId": source_id,
                "toolName": tool_name,
                "contractHash": contract_hash,
            }
        )
    ).hexdigest()


class InMemoryClassificationStore:
    """Fake offline com a mesma chave lógica e CAS do adapter Azure Table."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], McpToolClassification] = {}

    def get(
        self, tenant_key: str, source_id: str, tool_name: str, contract_hash: str
    ) -> McpToolClassification | None:
        return self._records.get(
            (tenant_key, _row_key(source_id, tool_name, contract_hash))
        )

    def replace(
        self, decision: McpToolClassification, expected_revision: int
    ) -> None:
        key = (
            decision.tenant_key,
            _row_key(decision.source_id, decision.tool_name, decision.contract_hash),
        )
        current = self._records.get(key)
        current_revision = current.revision if current is not None else 0
        if current_revision != expected_revision:
            raise ClassificationConflict("MCP_CLASSIFICATION_REVISION_CONFLICT")
        self._records[key] = decision


class TableClassificationStore:
    """Azure Table keyless com ETag e revisão explícita."""

    def __init__(self, account_url: str, table_name: str, credential: Any) -> None:
        from azure.data.tables import TableServiceClient

        service = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = service.create_table_if_not_exists(table_name)

    @staticmethod
    def _from_entity(entity: dict[str, Any]) -> McpToolClassification:
        return McpToolClassification(**json.loads(entity["payload"]))

    @staticmethod
    def _entity(decision: McpToolClassification) -> dict[str, Any]:
        return {
            "PartitionKey": decision.tenant_key,
            "RowKey": _row_key(
                decision.source_id, decision.tool_name, decision.contract_hash
            ),
            "payload": json.dumps(asdict(decision), separators=(",", ":")),
            "sourceId": decision.source_id,
            "toolName": decision.tool_name,
            "contractHash": decision.contract_hash,
            "revision": decision.revision,
        }

    def get(
        self, tenant_key: str, source_id: str, tool_name: str, contract_hash: str
    ) -> McpToolClassification | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            entity = self._table.get_entity(
                partition_key=tenant_key,
                row_key=_row_key(source_id, tool_name, contract_hash),
            )
        except ResourceNotFoundError:
            return None
        return self._from_entity(entity)

    def replace(
        self, decision: McpToolClassification, expected_revision: int
    ) -> None:
        from azure.core import MatchConditions
        from azure.core.exceptions import (
            HttpResponseError,
            ResourceExistsError,
            ResourceNotFoundError,
        )

        entity = self._entity(decision)
        try:
            if expected_revision == 0:
                self._table.create_entity(entity)
                return
            current = self._table.get_entity(
                partition_key=decision.tenant_key, row_key=entity["RowKey"]
            )
            if int(current.get("revision", 0)) != expected_revision:
                raise ClassificationConflict("MCP_CLASSIFICATION_REVISION_CONFLICT")
            self._table.update_entity(
                entity,
                etag=current.metadata["etag"],
                match_condition=MatchConditions.IfNotModified,
            )
        except (HttpResponseError, ResourceExistsError, ResourceNotFoundError) as exc:
            raise ClassificationConflict(
                "MCP_CLASSIFICATION_REVISION_CONFLICT"
            ) from exc


_memory_store = InMemoryClassificationStore()
_configured_store: ClassificationStore | None = None


def classification_store() -> ClassificationStore:
    global _configured_store
    if _configured_store is not None:
        return _configured_store

    from app.shared.settings import settings

    if settings.deployment_mode != "shared" or settings.tenant_store_backend == "memory":
        return _memory_store
    if not settings.tenant_store_account_url:
        raise RuntimeError("TENANT_STORE_ACCOUNT_URL is required for MCP classification")

    from azure.identity import DefaultAzureCredential

    _configured_store = TableClassificationStore(
        settings.tenant_store_account_url,
        "mcpToolClassifications",
        DefaultAzureCredential(),
    )
    return _configured_store


def _tenant_key() -> str:
    return current_tenant_id() or "self-hosted"


def _read_snapshot(snapshot_id: str) -> dict | None:
    return read_evidence(snapshot_id, scope=_tenant_key())


def _snapshot_tool(snapshot: dict, tool_name: str) -> dict | None:
    return next(
        (
            tool
            for tool in snapshot.get("tools", ())
            if isinstance(tool, dict) and tool.get("name") == tool_name
        ),
        None,
    )


def effective_tool_state(
    decision: McpToolClassification | None,
    annotations: dict[str, Any],
    *,
    permitted: bool = True,
    current: bool = True,
) -> dict[str, str | bool]:
    """Calcula o estado mais restritivo; metadata remota nunca concede read."""
    if not permitted:
        effect = "forbidden"
    elif decision is None or not current:
        effect = "quarantined"
    elif (
        decision.effect == "write"
        or annotations.get("destructiveHint") is True
        or annotations.get("readOnlyHint") is False
    ):
        effect = "write_requires_approval"
    else:
        effect = "read"
    return {
        "effect": effect,
        "allowed": effect in {"read", "write_requires_approval"},
        "requiresApproval": effect == "write_requires_approval",
    }


def derive_runtime_config(
    snapshot: dict[str, Any],
    tool_names: list[str] | tuple[str, ...],
    *,
    store: ClassificationStore | None = None,
    permitted: Callable[[str], bool] = lambda _name: True,
    current: bool = True,
) -> dict[str, Any]:
    """Deriva allowlist e aprovação; policy só pode remover tools."""
    source_id = str((snapshot.get("source") or {}).get("id") or "")
    target_store = store or classification_store()
    selected: list[dict[str, Any]] = []
    for tool_name in tool_names:
        tool = _snapshot_tool(snapshot, tool_name)
        if tool is None:
            selected.append(
                {"name": tool_name, "effect": "quarantined", "allowed": False}
            )
            continue
        contract_hash = str(tool.get("contractHash") or "")
        decision = target_store.get(
            _tenant_key(), source_id, tool_name, contract_hash
        )
        state = effective_tool_state(
            decision,
            tool.get("annotations") or {},
            permitted=permitted(tool_name),
            current=current,
        )
        selected.append({"name": tool_name, **state})

    reads = [item["name"] for item in selected if item["effect"] == "read"]
    writes = [
        item["name"]
        for item in selected
        if item["effect"] == "write_requires_approval"
    ]
    return {
        "allowedTools": reads + writes,
        "approvalMode": {
            "always_require_approval": writes,
            "never_require_approval": reads,
        },
        "tools": selected,
    }


def project_snapshot_classifications(
    snapshot_id: str,
    projection: dict[str, Any],
    *,
    store: ClassificationStore | None = None,
    snapshot_reader=_read_snapshot,
) -> dict[str, Any]:
    """Acrescenta estado efetivo à projeção sanitizada para consulta autenticada."""
    snapshot = snapshot_reader(snapshot_id)
    if snapshot is None or snapshot.get("tenantKey") != _tenant_key():
        raise ClassificationNotFound("MCP_SOURCE_NOT_FOUND")
    tool_names = [
        str(tool.get("name"))
        for tool in projection.get("tools", ())
        if isinstance(tool, dict) and tool.get("name")
    ]
    runtime = derive_runtime_config(
        snapshot,
        tool_names,
        store=store,
        current=projection.get("status") == "current" and not projection.get("drift"),
    )
    states = {item["name"]: item for item in runtime["tools"]}
    return {
        **projection,
        "tools": [
            {
                **tool,
                "effectiveEffect": states[str(tool["name"])]["effect"],
                "requiresApproval": states[str(tool["name"])].get(
                    "requiresApproval", False
                ),
            }
            for tool in projection.get("tools", ())
        ],
    }


def derive_snapshot_runtime(
    snapshot_id: str,
    tool_names: list[str] | tuple[str, ...],
    *,
    store: ClassificationStore | None = None,
    snapshot_reader=_read_snapshot,
    permitted: Callable[[str], bool] = lambda _name: True,
    current: bool = True,
) -> dict[str, Any]:
    """Resolve a evidência protegida e deriva a configuração do runtime."""
    snapshot = snapshot_reader(snapshot_id)
    if snapshot is None or snapshot.get("tenantKey") != _tenant_key():
        raise ClassificationNotFound("MCP_SOURCE_NOT_FOUND")
    return derive_runtime_config(
        snapshot,
        tool_names,
        store=store,
        permitted=permitted,
        current=current,
    )


def _validate_decision(effect: str, reason: str, expected_revision: int) -> str:
    if effect not in {"read", "write"} or not isinstance(expected_revision, int):
        raise ClassificationInvalid("MCP_CLASSIFICATION_INVALID")
    normalized = reason.strip() if isinstance(reason, str) else ""
    if not normalized or len(normalized) > 500 or expected_revision < 0:
        raise ClassificationInvalid("MCP_CLASSIFICATION_INVALID")
    return normalized


def _audit_classification(
    recorder,
    *,
    actor: str,
    summary: str,
    snapshot_id: str,
    detail: dict[str, Any],
) -> None:
    recorder(
        scope=_tenant_key(),
        actor=actor,
        kind="approval",
        summary=summary,
        ref=snapshot_id,
        detail=detail,
    )


def classify_mcp_tool(
    snapshot_id: str,
    tool_name: str,
    *,
    effect: str,
    reason: str,
    expected_revision: int,
    store: ClassificationStore | None = None,
    snapshot_reader=_read_snapshot,
    audit_recorder=record,
    actor: str | None = None,
) -> dict[str, Any]:
    """Cria ou substitui uma decisão vinculada ao hash exato do contrato."""
    normalized_reason = _validate_decision(effect, reason, expected_revision)

    snapshot = snapshot_reader(snapshot_id)
    if snapshot is None or snapshot.get("tenantKey") != _tenant_key():
        raise ClassificationNotFound("MCP_SOURCE_NOT_FOUND")
    tool = _snapshot_tool(snapshot, tool_name)
    source_id = str((snapshot.get("source") or {}).get("id") or "")
    contract_hash = str((tool or {}).get("contractHash") or "")
    if not source_id or len(contract_hash) != 64:
        raise ClassificationNotFound("MCP_SOURCE_NOT_FOUND")

    target_store = store or classification_store()
    decided_by = actor or current_actor()
    decision = McpToolClassification(
        tenant_key=_tenant_key(),
        source_id=source_id,
        tool_name=tool_name,
        contract_hash=contract_hash,
        effect=effect,
        reason=normalized_reason,
        revision=expected_revision + 1,
        decided_at=datetime.now(UTC).isoformat(timespec="seconds"),
        decided_by=decided_by,
    )
    _audit_classification(
        audit_recorder,
        actor=decided_by,
        summary="Classificação MCP solicitada",
        snapshot_id=snapshot_id,
        detail={
            "tool": tool_name,
            "contractHash": contract_hash,
            "effect": effect,
            "expectedRevision": expected_revision,
        },
    )
    try:
        target_store.replace(decision, expected_revision)
    except ClassificationConflict:
        _audit_classification(
            audit_recorder,
            actor=decided_by,
            summary="Classificação MCP em conflito",
            snapshot_id=snapshot_id,
            detail={"tool": tool_name, "expectedRevision": expected_revision},
        )
        raise
    state = effective_tool_state(decision, tool.get("annotations") or {})
    return {
        "snapshotId": snapshot_id,
        "sourceId": source_id,
        "toolName": tool_name,
        "contractHash": contract_hash,
        "effect": effect,
        "reason": normalized_reason,
        "revision": decision.revision,
        "decidedAt": decision.decided_at,
        "decidedBy": decided_by,
        "effectiveEffect": state["effect"],
    }
