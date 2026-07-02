"""resolve_tenant: onboarded tid → sets _current_tenant; unknown/suspended → 403.

Exercises the authorization step in isolation with an in-memory store (no Entra, no network).

    uv run python -m eval.tenant_resolution_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from fastapi import HTTPException

from app.core import auth
from app.core.tenant import TenantConfig, current_tenant_id, set_current_tenant
from app.core.tenant_store import InMemoryTenantStore, TenantRecord


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    store = InMemoryTenantStore()
    store.put(TenantRecord(tid="t-ok", name="n", tier="shared", status="active",
                           data_plane=TenantConfig()))
    store.put(TenantRecord(tid="t-susp", name="n", tier="shared", status="suspended",
                           data_plane=TenantConfig()))

    set_current_tenant(None)
    auth.resolve_tenant(SimpleNamespace(tid="t-ok"), store)
    check("onboarded tid resolves", current_tenant_id() == "t-ok")

    def denies(tid: str) -> bool:
        set_current_tenant(None)
        try:
            auth.resolve_tenant(SimpleNamespace(tid=tid), store)
            return False
        except HTTPException as e:
            return e.status_code == 403

    check("unknown tid → 403", denies("t-unknown"))
    check("suspended tid → 403", denies("t-susp"))

    set_current_tenant(None)
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tenant resolution + deny path holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
