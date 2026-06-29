"""Per-tenant record persistence, keyed by tid. Swappable: the InMemory fake is for tests,
TableStorage is the first real impl (cheapest — reuses the existing Storage account). Swap to
Cosmos/Postgres later = another class implementing TenantStore.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict
from typing import Protocol

from app.core.tenant import TenantConfig


@dataclass(frozen=True)
class TenantRecord:
    tid: str
    name: str
    tier: str            # shared | dedicated | self_hosted
    status: str          # active | suspended
    data_plane: TenantConfig


class TenantStore(Protocol):
    def get(self, tid: str) -> TenantRecord | None: ...
    def put(self, rec: TenantRecord) -> None: ...
    def list(self) -> list[TenantRecord]: ...


class InMemoryTenantStore:
    """Test/dev fake."""

    def __init__(self) -> None:
        self._by_tid: dict[str, TenantRecord] = {}

    def get(self, tid: str) -> TenantRecord | None:
        return self._by_tid.get(tid)

    def put(self, rec: TenantRecord) -> None:
        self._by_tid[rec.tid] = rec

    def list(self) -> list[TenantRecord]:
        return list(self._by_tid.values())


class TableStorageTenantStore:
    """Azure Table Storage (keyless) on the existing Storage account. PartitionKey=tid,
    RowKey='config'. data_plane is stored as a JSON property (Table props are flat/scalar).
    """

    def __init__(self, account_url: str, table_name: str, credential) -> None:
        from azure.data.tables import TableServiceClient  # lazy: only the shared mode needs it
        svc = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = svc.create_table_if_not_exists(table_name)

    def get(self, tid: str) -> TenantRecord | None:
        from azure.core.exceptions import ResourceNotFoundError
        try:
            e = self._table.get_entity(partition_key=tid, row_key="config")
        except ResourceNotFoundError:
            return None
        return TenantRecord(
            tid=tid, name=e["name"], tier=e["tier"], status=e["status"],
            data_plane=TenantConfig(**json.loads(e["data_plane"])),
        )

    def put(self, rec: TenantRecord) -> None:
        self._table.upsert_entity({
            "PartitionKey": rec.tid, "RowKey": "config",
            "name": rec.name, "tier": rec.tier, "status": rec.status,
            "data_plane": json.dumps(asdict(rec.data_plane)),
        })

    def list(self) -> list[TenantRecord]:
        out: list[TenantRecord] = []
        for e in self._table.list_entities():
            out.append(TenantRecord(
                tid=e["PartitionKey"], name=e["name"], tier=e["tier"], status=e["status"],
                data_plane=TenantConfig(**json.loads(e["data_plane"])),
            ))
        return out
