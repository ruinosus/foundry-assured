"""Area administration is tenant-scoped and uses optimistic concurrency.

    uv run python -m tests.tenancy.areas_api_test
"""

from __future__ import annotations

import sys

from fastapi import HTTPException, Response

from app.modules.tenancy import api
from app.modules.tenancy.internal import tenant_resolution
from app.modules.tenancy.internal.tenant import TenantConfig, set_current_tenant
from app.modules.tenancy.internal.tenant_store import InMemoryTenantStore, TenantRecord

AREA_ID = "11111111-1111-4111-8111-111111111111"
GROUP_ID = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"


def raises_status(call, status: int) -> bool:
    try:
        call()
        return False
    except HTTPException as exc:
        return exc.status_code == status


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    store = InMemoryTenantStore()
    for tenant_id in ("tenant-a", "tenant-b"):
        store.put(
            TenantRecord(
                tid=tenant_id,
                name=tenant_id,
                tier="shared",
                status="active",
                data_plane=TenantConfig(),
            )
        )

    original_store = tenant_resolution._tenant_store
    tenant_resolution._tenant_store = store
    try:
        set_current_tenant(store.get("tenant-a"))
        created = api.create_area(
            api.AreaCreateBody(id=AREA_ID, name="Platform", entra_group_ids=[GROUP_ID]),
            Response(),
        )
        check("create returns revision one", created["area"].revision == 1)
        check("tenant A stores the area", len(store.get("tenant-a").areas) == 1)
        check("tenant B remains untouched", store.get("tenant-b").areas == ())
        check(
            "duplicate id in the same tenant returns 409",
            raises_status(
                lambda: api.create_area(
                    api.AreaCreateBody(id=AREA_ID, name="Duplicate", entra_group_ids=[GROUP_ID]),
                    Response(),
                ),
                409,
            ),
        )
        check(
            "stale If-Match returns 412",
            raises_status(
                lambda: api.patch_area(
                    AREA_ID,
                    api.AreaPatchBody(name="Stale"),
                    Response(),
                    '"0"',
                ),
                412,
            ),
        )
        updated = api.patch_area(
            AREA_ID,
            api.AreaPatchBody(name="Platform Engineering", status="suspended"),
            Response(),
            '"1"',
        )
        check("patch increments revision", updated["area"].revision == 2)
        check("patch suspends without deleting", store.get("tenant-a").areas[0].status == "suspended")

        set_current_tenant(store.get("tenant-b"))
        check(
            "tenant B cannot patch tenant A area",
            raises_status(
                lambda: api.patch_area(
                    AREA_ID,
                    api.AreaPatchBody(name="Cross tenant"),
                    Response(),
                    '"2"',
                ),
                404,
            ),
        )
    finally:
        tenant_resolution._tenant_store = original_store
        set_current_tenant(None)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ area administration contract holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
