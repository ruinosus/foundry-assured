"""TenantStore round-trip via the in-memory fake (infra-free). Table Storage shares the
same interface and is exercised in the Chunk 3 E2E.

    uv run python -m eval.tenant_store_test
"""

from __future__ import annotations

import sys

from app.core.tenant import TenantConfig
from app.core.tenant_store import InMemoryTenantStore, TenantRecord


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    store = InMemoryTenantStore()
    rec = TenantRecord(
        tid="tenant-abc", name="Acme", tier="shared", status="active",
        data_plane=TenantConfig(foundry_model="gpt-5-mini"),
    )
    store.put(rec)
    check("get returns the stored record", store.get("tenant-abc") == rec)
    check("unknown tid → None (deny path)", store.get("nope") is None)
    check("list includes it", rec in store.list())

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tenant store (in-memory) holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
