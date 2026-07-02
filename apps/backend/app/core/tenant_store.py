"""Per-tenant record persistence, keyed by tid. Swappable: the InMemory fake is for tests,
TableStorage is the first real impl (cheapest — reuses the existing Storage account). Swap to
Cosmos/Postgres later = another class implementing TenantStore.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, asdict, replace
from typing import Protocol

from app.core.tenant import TenantConfig
from app.agents.mcp.registry import SERVERS


@dataclass(frozen=True)
class Connection:
    id: str
    kind: str                          # a registry server id VERBATIM: github | azdo | azure | entra | learn | m365
    label: str
    endpoint: str = ""                 # per-connection target, e.g. the Azure DevOps org that fills the registry URL {org}
    foundry_connection_id: str = ""    # the Foundry project connection that brokers auth (Microsoft-native)
    keyvault_ref: str = ""             # DEPRECATED (C/ADR-009): the build no longer reads it; kept for back-compat
    min_role_read: str = "Reader"
    min_role_write: str = "Author"
    enabled: bool = True
    # NO secret / auth_method — Foundry connections / Key Vault authenticate (ADR-005/008).


@dataclass(frozen=True)
class TenantRecord:
    tid: str
    name: str
    tier: str            # shared | dedicated | self_hosted
    status: str          # active | suspended
    data_plane: TenantConfig
    connections: tuple[Connection, ...] = ()   # NEW (keep after data_plane)
    enabled_domains: tuple[str, ...] = ()   # NEW (D-runtime) — per-tenant license entitlement (ADR-010)


def validate_kind(kind: str) -> bool:
    """True if `kind` is a registry server id (the catalog is the source of truth)."""
    return any(s.id == kind for s in SERVERS)


def with_connection(rec: TenantRecord, conn: Connection) -> TenantRecord:
    """Return a new record with `conn` added/replaced (by id) — upsert."""
    others = tuple(c for c in rec.connections if c.id != conn.id)
    return replace(rec, connections=others + (conn,))


def without_connection(rec: TenantRecord, conn_id: str) -> TenantRecord:
    """Return a new record with the connection `conn_id` removed."""
    return replace(rec, connections=tuple(c for c in rec.connections if c.id != conn_id))


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


def _record_from_entity(e, tid: str | None = None) -> TenantRecord:
    conns = tuple(Connection(**c) for c in json.loads(e.get("connections") or "[]"))
    return TenantRecord(
        tid=tid or e["PartitionKey"], name=e["name"], tier=e["tier"], status=e["status"],
        data_plane=TenantConfig(**json.loads(e["data_plane"])),
        connections=conns,
        enabled_domains=tuple(json.loads(e.get("enabled_domains") or "[]")),
    )


class TableStorageTenantStore:
    """Azure Table Storage (keyless) on the existing Storage account. PartitionKey=tid,
    RowKey='config'. data_plane is stored as a JSON property (Table props are flat/scalar).
    """

    def __init__(self, account_url: str, table_name: str, credential) -> None:
        # Imported at construction, not module load — and this class is ONLY instantiated in
        # shared mode (the boot-time store factory, Task 6), so single-tenant never imports
        # azure-data-tables. API verified against azure-data-tables 12.7.0 (endpoint= kwarg).
        from azure.data.tables import TableServiceClient
        svc = TableServiceClient(endpoint=account_url, credential=credential)
        self._table = svc.create_table_if_not_exists(table_name)

    def get(self, tid: str) -> TenantRecord | None:
        from azure.core.exceptions import ResourceNotFoundError
        try:
            e = self._table.get_entity(partition_key=tid, row_key="config")
        except ResourceNotFoundError:
            return None
        return _record_from_entity(e, tid)

    def put(self, rec: TenantRecord) -> None:
        self._table.upsert_entity({
            "PartitionKey": rec.tid, "RowKey": "config",
            "name": rec.name, "tier": rec.tier, "status": rec.status,
            "data_plane": json.dumps(asdict(rec.data_plane)),
            "connections": json.dumps([asdict(c) for c in rec.connections]),
            "enabled_domains": json.dumps(list(rec.enabled_domains)),
        })

    def list(self) -> list[TenantRecord]:
        out: list[TenantRecord] = []
        for e in self._table.list_entities():
            out.append(_record_from_entity(e))
        return out
