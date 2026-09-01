"""Tenant, Entra groups and App Roles intersect into an authorized authoring area.

    uv run python -m tests.tenancy.area_context_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.modules.admin import api_me
from app.modules.tenancy.internal import tenant_resolution
from app.modules.tenancy.internal.areas import authorized_areas, resolve_area
from app.modules.tenancy.internal.tenant import TenantConfig
from app.modules.tenancy.internal.tenant_store import AuthoringArea, TenantRecord
from app.shared import auth


def main() -> int:
    failures: list[str] = []

    def check(name: str, condition: bool) -> None:
        print(f"  {'✓' if condition else '✗'} {name}")
        if not condition:
            failures.append(name)

    area_a = AuthoringArea(
        id="11111111-1111-4111-8111-111111111111",
        name="Platform A",
        entra_group_ids=("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",),
    )
    area_b = AuthoringArea(
        id="22222222-2222-4222-8222-222222222222",
        name="Platform B",
        entra_group_ids=("bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb",),
    )
    tenant_a = TenantRecord(
        tid="tenant-a",
        name="Tenant A",
        tier="shared",
        status="active",
        data_plane=TenantConfig(),
        areas=(area_a, area_b),
    )
    tenant_b = TenantRecord(
        tid="tenant-b",
        name="Tenant B",
        tier="shared",
        status="active",
        data_plane=TenantConfig(),
        areas=(area_b,),
    )
    reader_admin = SimpleNamespace(
        tid="tenant-a",
        groups=["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"],
        roles=["Reader", "Admin"],
    )

    visible = authorized_areas(reader_admin, tenant_a)
    check("tenant A sees only the area granted by its Entra group", [area.id for area in visible] == [area_a.id])
    check("requested area A resolves", resolve_area(reader_admin, tenant_a, area_a.id).id == area_a.id)
    check("requested area B does not grant authority", resolve_area(reader_admin, tenant_a, area_b.id) is None)
    check("Admin does not imply Approver", "Approver" not in visible[0].permissions)
    check("validated App Roles remain effective", visible[0].permissions == ("Admin", "Reader"))
    check("tenant A identity cannot resolve against tenant B", resolve_area(reader_admin, tenant_b, area_b.id) is None)

    original_store = tenant_resolution._tenant_store
    original_settings = api_me.settings
    tenant_resolution._tenant_store = SimpleNamespace(get=lambda tenant_id: tenant_a if tenant_id == tenant_a.tid else None)
    api_me.settings = SimpleNamespace(auth_enabled=True)
    auth.set_current_user(reader_admin)
    from app.modules.tenancy.internal.tenant import set_current_tenant

    set_current_tenant(tenant_a)
    try:
        identity = api_me.me()
        check("GET /me returns the resolved tenant", identity["tenant_id"] == tenant_a.tid)
        check("GET /me returns only authorized areas", [area["id"] for area in identity["areas"]] == [area_a.id])
        check("GET /me does not expose Entra group ids", "entra_group_ids" not in identity["areas"][0])
    finally:
        tenant_resolution._tenant_store = original_store
        api_me.settings = original_settings
        auth.set_current_user(None)
        set_current_tenant(None)

    suspended = SimpleNamespace(
        tid="tenant-a",
        groups=["aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"],
        roles=["Reader"],
    )
    suspended_area = AuthoringArea(
        id="33333333-3333-4333-8333-333333333333",
        name="Suspended",
        status="suspended",
        entra_group_ids=("aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa",),
    )
    suspended_tenant = TenantRecord(
        tid="tenant-a",
        name="Tenant A",
        tier="shared",
        status="active",
        data_plane=TenantConfig(),
        areas=(suspended_area,),
    )
    check("suspended area is fail-closed", authorized_areas(suspended, suspended_tenant) == ())

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tenant-area authorization holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
