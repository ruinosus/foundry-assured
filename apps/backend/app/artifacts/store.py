"""Artifact stores — metadata (Table) + content (Blob), each with an in-memory fake.

Mirrors app/core/tenant_store.py: a Protocol + InMemory fake for dev/CI + an
Azure impl that lazily imports the SDK at construction time.
"""
from __future__ import annotations

from typing import Protocol

from app.artifacts.models import ArtifactRecord


class ArtifactStore(Protocol):
    def get(self, tenant_id: str, artifact_id: str) -> ArtifactRecord | None: ...
    def put(self, rec: ArtifactRecord) -> None: ...
    def list(self, tenant_id: str) -> list[ArtifactRecord]: ...


class InMemoryArtifactStore:
    """Test/dev fake."""

    def __init__(self) -> None:
        self._by_key: dict[tuple[str, str], ArtifactRecord] = {}

    def get(self, tenant_id: str, artifact_id: str) -> ArtifactRecord | None:
        return self._by_key.get((tenant_id, artifact_id))

    def put(self, rec: ArtifactRecord) -> None:
        self._by_key[(rec.tenant_id, rec.id)] = rec

    def list(self, tenant_id: str) -> list[ArtifactRecord]:
        return [r for (t, _), r in self._by_key.items() if t == tenant_id]


_FIELDS = (
    "title", "description", "type", "status", "created_by", "created_at",
    "updated_at", "blob_path", "version", "approved_by", "approved_at",
    "content_hash",
)


def _record_from_entity(e) -> ArtifactRecord:
    return ArtifactRecord(
        id=e["RowKey"],
        tenant_id=e["PartitionKey"],
        title=e.get("title", ""),
        description=e.get("description", ""),
        type=e.get("type", ""),
        status=e.get("status", ""),
        created_by=e.get("created_by", ""),
        created_at=e.get("created_at", ""),
        updated_at=e.get("updated_at", ""),
        blob_path=e.get("blob_path", ""),
        version=int(e.get("version", 1)),
        approved_by=e.get("approved_by") or None,
        approved_at=e.get("approved_at") or None,
        content_hash=e.get("content_hash") or None,
    )


class TableArtifactStore:
    """Azure Table Storage (keyless). PartitionKey=tenant_id, RowKey=artifact_id."""

    def __init__(self, account_url: str, table_name: str, credential) -> None:
        from azure.data.tables import TableServiceClient  # lazy, construction-time

        svc = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = svc.create_table_if_not_exists(table_name)

    def get(self, tenant_id: str, artifact_id: str) -> ArtifactRecord | None:
        from azure.core.exceptions import ResourceNotFoundError

        try:
            e = self._table.get_entity(partition_key=tenant_id, row_key=artifact_id)
        except ResourceNotFoundError:
            return None
        return _record_from_entity(e)

    def put(self, rec: ArtifactRecord) -> None:
        entity = {"PartitionKey": rec.tenant_id, "RowKey": rec.id}
        for f in _FIELDS:
            val = getattr(rec, f)
            entity[f] = "" if val is None else val
        self._table.upsert_entity(entity)

    def list(self, tenant_id: str) -> list[ArtifactRecord]:
        rows = self._table.query_entities(
            "PartitionKey eq @t", parameters={"t": tenant_id}
        )
        return [_record_from_entity(e) for e in rows]
