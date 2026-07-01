"""enabled_domains survives the Table entity round-trip, and defaults to () on legacy records.

Infra-free — exercises the pure (de)serialization helpers with a dict standing in for a
Table entity (no azure-data-tables, no network).

    uv run python -m eval.enabled_domains_roundtrip_test
"""

from __future__ import annotations

import json
import sys
from dataclasses import asdict

from app.core.tenant import TenantConfig
from app.core.tenant_store import TenantRecord, _record_from_entity


def _entity(rec: TenantRecord) -> dict:
    return {
        "PartitionKey": rec.tid, "RowKey": "config",
        "name": rec.name, "tier": rec.tier, "status": rec.status,
        "data_plane": json.dumps(asdict(rec.data_plane)),
        "connections": json.dumps([asdict(c) for c in rec.connections]),
        "enabled_domains": json.dumps(list(rec.enabled_domains)),
    }


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    rec = TenantRecord(tid="t1", name="n", tier="shared", status="active",
                       data_plane=TenantConfig(), enabled_domains=("helpdesk", "platform"))
    back = _record_from_entity(_entity(rec), "t1")
    check("enabled_domains round-trips", back.enabled_domains == ("helpdesk", "platform"))

    legacy = {
        "PartitionKey": "t2", "RowKey": "config", "name": "n", "tier": "shared",
        "status": "active", "data_plane": json.dumps(asdict(TenantConfig())),
        "connections": "[]",
    }
    check("legacy entity → enabled_domains == ()", _record_from_entity(legacy, "t2").enabled_domains == ())

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ enabled_domains serialization holds (incl. legacy default).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
