"""F04: referências de Connection são resolvidas somente no tenant atual."""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.modules.tenancy import public as tenancy
from app.modules.tenancy.public import (
    Connection,
    InMemoryTenantStore,
    TenantConfig,
    TenantRecord,
    set_current_tenant,
)


def main() -> int:
    store = InMemoryTenantStore()
    for tid, foundry_id in (("tenant-a", "foundry-a"), ("tenant-b", "foundry-b")):
        store.put(
            TenantRecord(
                tid=tid,
                name=tid,
                tier="shared",
                status="active",
                data_plane=TenantConfig(),
                connections=(
                    Connection(
                        id="same-name",
                        kind="github",
                        label="GitHub",
                        area_id="area-a" if tid == "tenant-a" else "area-b",
                        foundry_connection_id=foundry_id,
                    ),
                ),
            )
        )

    original_store = tenancy.tenant_store
    original_current_area = tenancy.current_area
    tenancy.tenant_store = lambda: store
    try:
        set_current_tenant(SimpleNamespace(tid="tenant-a"))
        first = tenancy.current_connection("same-name")
        tenancy.current_area = lambda: SimpleNamespace(id="area-b")
        cross_area = tenancy.current_connection("same-name")
        tenancy.current_area = lambda: SimpleNamespace(id="area-a")
        owner_area = tenancy.current_connection("same-name")
        tenancy.current_area = original_current_area
        set_current_tenant(SimpleNamespace(tid="tenant-b"))
        second = tenancy.current_connection("same-name")
        missing = tenancy.current_connection("only-in-another-tenant")
    finally:
        tenancy.tenant_store = original_store
        tenancy.current_area = original_current_area
        set_current_tenant(None)

    checks = {
        "tenant A recebe sua referência": first.foundry_connection_id == "foundry-a",
        "área proprietária recebe sua referência": owner_area.foundry_connection_id == "foundry-a",
        "referência não atravessa área": cross_area is None,
        "tenant B recebe sua referência": second.foundry_connection_id == "foundry-b",
        "referência ausente não atravessa tenant": missing is None,
    }
    failures = [name for name, ok in checks.items() if not ok]
    for name, ok in checks.items():
        print(f"  {'✓' if ok else '✗'} {name}")
    print(f"\n{'❌' if failures else '✅'} {len(failures)} failure(s)")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
