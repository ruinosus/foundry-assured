"""The connection write ops only mutate the targeted record, never another tenant's; bad
input is rejected. Mirrors what the /tenant endpoints do (read-modify-write on one record).

    uv run python -m eval.tenant_scope_test
"""

from __future__ import annotations

import sys

from app.core.tenant import TenantConfig
from app.core.tenant_store import (
    Connection, InMemoryTenantStore, TenantRecord, set_server_catalog, validate_kind, with_connection,
)
# The catalog is injected by the composition root at boot (ADR-017); tests inject it too,
# because tenancy no longer reaches into the platform registry for it.
from app.agents.mcp.registry import SERVERS
set_server_catalog(server.id for server in SERVERS)



def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    store = InMemoryTenantStore()
    for tid in ("t-a", "t-b"):
        store.put(TenantRecord(tid=tid, name=tid, tier="shared", status="active",
                               data_plane=TenantConfig()))

    # The read-modify-write an endpoint does for current_tenant_id() == "t-a":
    rec_a = store.get("t-a")
    store.put(with_connection(rec_a, Connection(id="c1", kind="github", label="GH")))

    check("t-a got the connection", len(store.get("t-a").connections) == 1)
    check("t-b is untouched", store.get("t-b").connections == ())
    check("bad kind rejected (endpoint would 422)", not validate_kind("evil"))

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tenant-scoped connection ops hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
