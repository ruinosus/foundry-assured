"""TenantRecord with embedded connections round-trips through the in-memory fake (infra-free).

    uv run python -m eval.connection_store_test
"""

from __future__ import annotations

import sys

from app.core.tenant import TenantConfig
from app.core.tenant_store import Connection, InMemoryTenantStore, TenantRecord


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    conn = Connection(id="gh-acme", kind="github", label="Acme GitHub",
                      foundry_connection_id="conn:gh-acme")
    rec = TenantRecord(tid="t1", name="Acme", tier="shared", status="active",
                       data_plane=TenantConfig(), connections=(conn,))
    store = InMemoryTenantStore()
    store.put(rec)
    got = store.get("t1")
    check("record round-trips with its connection", got == rec)
    check("connection is preserved", got.connections[0].foundry_connection_id == "conn:gh-acme")

    bare = TenantRecord(tid="t2", name="B", tier="shared", status="active",
                        data_plane=TenantConfig())
    store.put(bare)
    check("record without connections defaults to ()", store.get("t2").connections == ())

    check("Connection has NO secret field",
          not any(f in Connection.__dataclass_fields__ for f in ("secret", "secret_ref", "auth_method", "pat", "token")))

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ connection store round-trip holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
