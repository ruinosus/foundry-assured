"""Drift tenant-safe entre snapshots MCP sanitizados e imutáveis."""

from __future__ import annotations

import hashlib
import json
from dataclasses import asdict, dataclass, replace
from datetime import UTC, datetime
from typing import Any, Protocol, cast

from app.modules.audit.public import actor as current_actor
from app.modules.audit.public import read_evidence, record
from app.modules.tenancy.public import current_authoring_scope_key


class SnapshotReviewInvalid(ValueError):
    """O snapshot não satisfaz as pré-condições de review."""


class SnapshotReviewConflict(RuntimeError):
    """A projeção da source mudou desde a leitura do Admin."""


class SnapshotReviewNotFound(LookupError):
    """A source ou snapshot não existe no tenant atual."""


@dataclass(frozen=True)
class McpSourceState:
    tenant_key: str
    source_id: str
    source: dict[str, Any]
    status: str
    latest_snapshot_id: str | None
    latest_snapshot_hash: str | None
    reviewed_snapshot_id: str | None
    reviewed_snapshot_hash: str | None
    reviewed_classifications: dict[str, str]
    last_success_at: str | None
    last_attempt_at: str
    drift: dict[str, Any] | None
    error_code: str | None
    revision: int


class McpSourceStore(Protocol):
    def get(self, tenant_key: str, source_id: str) -> McpSourceState | None: ...

    def replace(self, state: McpSourceState, expected_revision: int) -> None: ...


class InMemoryMcpSourceStore:
    """Fake offline com o mesmo CAS da projeção Azure Table."""

    def __init__(self) -> None:
        self._records: dict[tuple[str, str], McpSourceState] = {}

    def get(self, tenant_key: str, source_id: str) -> McpSourceState | None:
        return self._records.get((tenant_key, source_id))

    def replace(self, state: McpSourceState, expected_revision: int) -> None:
        key = (state.tenant_key, state.source_id)
        current = self._records.get(key)
        revision = current.revision if current is not None else 0
        if revision != expected_revision:
            raise SnapshotReviewConflict("MCP_SOURCE_REVISION_CONFLICT")
        self._records[key] = state


def _source_row_key(source_id: str) -> str:
    return hashlib.sha256(source_id.encode()).hexdigest()


class TableMcpSourceStore:
    """Projeção Azure Table autenticada por identidade gerenciada."""

    def __init__(self, account_url: str, table_name: str, credential: Any) -> None:
        from azure.data.tables import TableServiceClient

        service = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = service.create_table_if_not_exists(table_name)

    def get(self, tenant_key: str, source_id: str) -> McpSourceState | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            entity = self._table.get_entity(
                partition_key=tenant_key,
                row_key=_source_row_key(source_id),
            )
        except ResourceNotFoundError:
            return None
        return McpSourceState(**json.loads(entity["payload"]))

    def replace(self, state: McpSourceState, expected_revision: int) -> None:
        from azure.core import MatchConditions
        from azure.core.exceptions import (
            HttpResponseError,
            ResourceExistsError,
            ResourceNotFoundError,
        )

        entity = {
            "PartitionKey": state.tenant_key,
            "RowKey": _source_row_key(state.source_id),
            "payload": json.dumps(asdict(state), separators=(",", ":")),
            "sourceId": state.source_id,
            "status": state.status,
            "revision": state.revision,
        }
        try:
            if expected_revision == 0:
                self._table.create_entity(entity)
                return
            current = self._table.get_entity(
                partition_key=state.tenant_key,
                row_key=entity["RowKey"],
            )
            if int(current.get("revision", 0)) != expected_revision:
                raise SnapshotReviewConflict("MCP_SOURCE_REVISION_CONFLICT")
            self._table.update_entity(
                entity,
                etag=current.metadata["etag"],
                match_condition=MatchConditions.IfNotModified,
            )
        except (HttpResponseError, ResourceExistsError, ResourceNotFoundError) as exc:
            raise SnapshotReviewConflict("MCP_SOURCE_REVISION_CONFLICT") from exc


_memory_store = InMemoryMcpSourceStore()
_configured_store: McpSourceStore | None = None


def mcp_source_store() -> McpSourceStore:
    global _configured_store
    if _configured_store is not None:
        return _configured_store

    from app.shared.settings import settings

    if settings.deployment_mode != "shared" or settings.tenant_store_backend == "memory":
        return _memory_store
    if not settings.tenant_store_account_url:
        raise RuntimeError("TENANT_STORE_ACCOUNT_URL is required for MCP source state")

    from azure.identity import DefaultAzureCredential

    _configured_store = TableMcpSourceStore(
        settings.tenant_store_account_url,
        "mcpSourceStates",
        DefaultAzureCredential(),
    )
    return _configured_store


def _tenant_key() -> str:
    return current_authoring_scope_key()


def _snapshot_reader(snapshot_id: str) -> dict[str, Any] | None:
    return read_evidence(snapshot_id, scope=_tenant_key())


def _classifications(snapshot: dict[str, Any]) -> dict[str, str]:
    from app.modules.platform_ops.internal.mcp_classification import (
        classification_store,
    )

    source_id = str((snapshot.get("source") or {}).get("id") or "")
    store = classification_store()
    result = {}
    for tool in snapshot.get("tools", ()):
        if not isinstance(tool, dict) or not tool.get("name"):
            continue
        decision = store.get(
            _tenant_key(),
            source_id,
            str(tool["name"]),
            str(tool.get("contractHash") or ""),
        )
        if decision is not None:
            result[str(tool["name"])] = decision.effect
    return result


def _projection(state: McpSourceState) -> dict[str, Any]:
    return {
        "source": state.source,
        "status": state.status,
        "latestSnapshotId": state.latest_snapshot_id,
        "reviewedSnapshotId": state.reviewed_snapshot_id,
        "lastSuccessAt": state.last_success_at,
        "lastAttemptAt": state.last_attempt_at,
        "drift": state.drift,
        "errorCode": state.error_code,
        "revision": state.revision,
    }


def _source_identity(source: dict[str, Any]) -> dict[str, Any]:
    return {
        key: source[key]
        for key in ("kind", "id", "name", "resolvedVersion")
        if source.get(key) is not None
    }


def _tools(snapshot: dict[str, Any]) -> dict[str, dict[str, Any]]:
    return {
        str(tool["name"]): tool
        for tool in snapshot.get("tools", ())
        if isinstance(tool, dict) and tool.get("name")
    }


def _tool_changes(
    name: str,
    previous: dict[str, dict[str, Any]],
    current: dict[str, dict[str, Any]],
    reviewed: dict[str, str],
    classified: dict[str, str],
) -> list[str]:
    if name not in previous:
        return ["added"]
    if name not in current:
        return ["removed"]
    if previous[name].get("contractHash") != current[name].get("contractHash"):
        return ["contract"]
    if reviewed.get(name) != classified.get(name):
        return ["classification"]
    return []


def compare_mcp_snapshots(
    previous: dict[str, Any],
    current: dict[str, Any],
    *,
    reviewed_classifications: dict[str, str] | None = None,
    current_classifications: dict[str, str] | None = None,
) -> dict[str, Any]:
    """Compara identidade, versão, contratos e classificação por tool."""
    previous_source = previous.get("source") or {}
    current_source = current.get("source") or {}
    source_changed = (
        previous_source.get("kind") != current_source.get("kind")
        or previous_source.get("id") != current_source.get("id")
    )
    version_changed = str(previous_source.get("resolvedVersion") or "") != str(
        current_source.get("resolvedVersion") or ""
    )
    previous_tools = _tools(previous)
    current_tools = _tools(current)
    reviewed = reviewed_classifications or {}
    classified = current_classifications or reviewed
    changes: list[dict[str, Any]] = []

    for name in sorted(previous_tools.keys() | current_tools.keys()):
        tool_changes = _tool_changes(
            name, previous_tools, current_tools, reviewed, classified
        )
        if tool_changes:
            changes.append(
                {"name": name, "changes": tool_changes, "status": "quarantined"}
            )

    quarantined = [item["name"] for item in changes]
    requires_full_review = source_changed or version_changed
    return {
        "blocking": bool(quarantined or requires_full_review),
        "sourceChanged": source_changed,
        "versionChanged": version_changed,
        "requiresFullReview": requires_full_review,
        "quarantinedTools": quarantined,
        "tools": changes,
    }


def _reviewed_snapshot(current: McpSourceState | None, snapshot_reader) -> dict:
    if current is None or not current.reviewed_snapshot_id:
        return {}
    return snapshot_reader(current.reviewed_snapshot_id) or {}


def _observed_state(
    *,
    tenant_key: str,
    source_id: str,
    source: dict[str, Any],
    snapshot_id: str,
    snapshot_hash: str,
    observed_at: str,
    drift: dict[str, Any],
    current: McpSourceState | None,
) -> McpSourceState:
    revision = current.revision if current else 0
    return McpSourceState(
        tenant_key=tenant_key,
        source_id=source_id,
        source=_source_identity(source),
        status="current",
        latest_snapshot_id=snapshot_id,
        latest_snapshot_hash=snapshot_hash,
        reviewed_snapshot_id=current.reviewed_snapshot_id if current else None,
        reviewed_snapshot_hash=current.reviewed_snapshot_hash if current else None,
        reviewed_classifications=(
            dict(current.reviewed_classifications) if current else {}
        ),
        last_success_at=observed_at,
        last_attempt_at=observed_at,
        drift=drift if drift["blocking"] else None,
        error_code=None,
        revision=revision + 1,
    )


def observe_mcp_snapshot(
    snapshot: dict[str, Any],
    *,
    store: McpSourceStore | None = None,
    snapshot_reader=_snapshot_reader,
    classification_reader=_classifications,
) -> dict[str, Any]:
    """Atualiza somente a projeção após uma observação já gravada no Blob."""
    tenant_key = _tenant_key()
    if snapshot.get("tenantKey") != tenant_key:
        raise SnapshotReviewInvalid("MCP_SOURCE_NOT_FOUND")
    source = snapshot.get("source") or {}
    source_id = str(source.get("id") or "")
    snapshot_id = str(snapshot.get("snapshotId") or "")
    snapshot_hash = str(snapshot.get("snapshotHash") or "")
    if not source_id or not snapshot_id or len(snapshot_hash) != 64:
        raise SnapshotReviewInvalid("MCP_SNAPSHOT_INVALID")

    target_store = store or mcp_source_store()
    current = target_store.get(tenant_key, source_id)
    previous = _reviewed_snapshot(current, snapshot_reader)
    if not previous:
        previous = {"source": source, "tools": []}
    classifications = classification_reader(snapshot)
    drift = compare_mcp_snapshots(
        previous,
        snapshot,
        reviewed_classifications=(
            current.reviewed_classifications if current is not None else {}
        ),
        current_classifications=classifications,
    )
    observed_at = str(snapshot.get("observedAt") or datetime.now(UTC).isoformat())
    revision = current.revision if current else 0
    state = _observed_state(
        tenant_key=tenant_key,
        source_id=source_id,
        source=source,
        snapshot_id=snapshot_id,
        snapshot_hash=snapshot_hash,
        observed_at=observed_at,
        drift=drift,
        current=current,
    )
    target_store.replace(state, revision)
    return _projection(state)


def review_mcp_snapshot(
    snapshot_id: str,
    *,
    reason: str,
    expected_revision: int,
    store: McpSourceStore | None = None,
    snapshot_reader=_snapshot_reader,
    classification_reader=_classifications,
    audit_recorder=record,
    actor: str | None = None,
) -> dict[str, Any]:
    """Promove um snapshot somente após classificação completa e auditável."""
    normalized_reason = reason.strip() if isinstance(reason, str) else ""
    if (
        not normalized_reason
        or len(normalized_reason) > 500
        or not isinstance(expected_revision, int)
        or expected_revision < 1
    ):
        raise SnapshotReviewInvalid("MCP_SNAPSHOT_REVIEW_INVALID")
    snapshot = snapshot_reader(snapshot_id)
    if snapshot is None or snapshot.get("tenantKey") != _tenant_key():
        raise SnapshotReviewNotFound("MCP_SOURCE_NOT_FOUND")
    source_id = str((snapshot.get("source") or {}).get("id") or "")
    target_store = store or mcp_source_store()
    current = target_store.get(_tenant_key(), source_id)
    if (
        current is None
        or current.latest_snapshot_id != snapshot_id
        or current.revision != expected_revision
    ):
        raise SnapshotReviewConflict("MCP_SOURCE_REVISION_CONFLICT")
    assert current is not None
    classifications = classification_reader(snapshot)
    tool_names = {
        str(tool["name"])
        for tool in snapshot.get("tools", ())
        if isinstance(tool, dict) and tool.get("name")
    }
    if set(classifications) != tool_names:
        raise SnapshotReviewInvalid("MCP_CLASSIFICATION_INCOMPLETE")

    decided_by = actor or current_actor()
    audit_recorder(
        scope=_tenant_key(),
        actor=decided_by,
        kind="approval",
        summary="Snapshot MCP revisado",
        ref=snapshot_id,
        detail={
            "sourceId": source_id,
            "snapshotHash": snapshot.get("snapshotHash"),
            "toolCount": len(tool_names),
            "expectedRevision": expected_revision,
            "reason": normalized_reason,
        },
    )
    reviewed = cast(
        "McpSourceState",
        replace(
            current,
            status="current",
            reviewed_snapshot_id=snapshot_id,
            reviewed_snapshot_hash=str(snapshot.get("snapshotHash") or ""),
            reviewed_classifications=dict(classifications),
            drift=None,
            error_code=None,
            revision=expected_revision + 1,
        ),
    )
    target_store.replace(reviewed, expected_revision)
    return _projection(reviewed)


def mark_mcp_source_stale(
    source: dict[str, Any],
    *,
    error_code: str,
    store: McpSourceStore | None = None,
) -> dict[str, Any]:
    """Preserva o último sucesso e registra somente estado operacional stale."""
    source_id = str(source.get("id") or "")
    if not source_id or not error_code.startswith("MCP_") or len(error_code) > 64:
        raise SnapshotReviewInvalid("MCP_SOURCE_STATE_INVALID")
    target_store = store or mcp_source_store()
    current = target_store.get(_tenant_key(), source_id)
    revision = current.revision if current is not None else 0
    now = datetime.now(UTC).isoformat(timespec="seconds")
    stale = McpSourceState(
        tenant_key=_tenant_key(),
        source_id=source_id,
        source=_source_identity(source),
        status="stale",
        latest_snapshot_id=current.latest_snapshot_id if current else None,
        latest_snapshot_hash=current.latest_snapshot_hash if current else None,
        reviewed_snapshot_id=current.reviewed_snapshot_id if current else None,
        reviewed_snapshot_hash=current.reviewed_snapshot_hash if current else None,
        reviewed_classifications=(
            dict(current.reviewed_classifications) if current else {}
        ),
        last_success_at=current.last_success_at if current else None,
        last_attempt_at=now,
        drift=current.drift if current else None,
        error_code=error_code,
        revision=revision + 1,
    )
    target_store.replace(stale, revision)
    return _projection(stale)


def get_mcp_source(
    source_id: str, *, store: McpSourceStore | None = None
) -> dict[str, Any] | None:
    state = (store or mcp_source_store()).get(_tenant_key(), source_id)
    return _projection(state) if state is not None else None


def source_tool_is_current(
    snapshot_id: str,
    tool_name: str,
    *,
    source_id: str,
    store: McpSourceStore | None = None,
) -> bool:
    """Decide antes da rede se uma tool do snapshot continua executável."""
    status = source_tool_current_state(
        snapshot_id,
        tool_name,
        source_id=source_id,
        store=store,
    )
    return status is True


def source_tool_current_state(
    snapshot_id: str,
    tool_name: str,
    *,
    source_id: str,
    classification_effect: str | None = None,
    store: McpSourceStore | None = None,
) -> bool | None:
    """Retorna None para snapshot legado ainda não rastreado pela projeção."""
    state = (store or mcp_source_store()).get(_tenant_key(), source_id)
    if state is None:
        return None
    if state.status != "current":
        return False
    if snapshot_id not in {state.latest_snapshot_id, state.reviewed_snapshot_id}:
        return False
    quarantined = set((state.drift or {}).get("quarantinedTools", ()))
    if tool_name in quarantined:
        return False
    reviewed_effect = state.reviewed_classifications.get(tool_name)
    return not (
        classification_effect is not None
        and reviewed_effect is not None
        and classification_effect != reviewed_effect
    )
