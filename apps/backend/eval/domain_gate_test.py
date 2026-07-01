"""require_domain: entitled domain passes; missing entitlement / no tenant → 403.

Infra-free — fakes _current_tenant directly, no Entra, no store, no network.

    uv run python -m eval.domain_gate_test
"""

from __future__ import annotations

import asyncio
import sys

from fastapi import HTTPException

from app.core.tenant import (
    DOMAIN_IDS,
    TenantConfig,
    require_domain,
    set_current_tenant,
)
from app.core.tenant_store import TenantRecord


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    check("DOMAIN_IDS is the four-domain catalog",
          DOMAIN_IDS == ("helpdesk", "cockpit", "selfwiki", "platform"))

    # The inner check ignores its dependency-wiring `_user` arg and reads `_current_tenant`,
    # so the test calls `gate(_user=None)` directly (bypassing the Depends(require_user)).
    gate = require_domain("cockpit")

    def _set(enabled: tuple[str, ...] | None) -> None:
        rec = None if enabled is None else TenantRecord(
            tid="t", name="t", tier="shared", status="active",
            data_plane=TenantConfig(), enabled_domains=enabled,
        )
        set_current_tenant(rec)

    def allowed(enabled: tuple[str, ...] | None) -> bool:
        _set(enabled)
        try:
            asyncio.run(gate(_user=None))
            return True
        except HTTPException:
            return False

    def denies(enabled: tuple[str, ...] | None) -> bool:
        _set(enabled)
        try:
            asyncio.run(gate(_user=None))
            return False
        except HTTPException as e:
            return e.status_code == 403

    check("entitled domain passes", allowed(("cockpit", "helpdesk")))
    check("domain not in entitlement → 403", denies(("helpdesk",)))
    check("empty entitlement → 403", denies(()))
    check("no resolved tenant → 403", denies(None))

    set_current_tenant(None)
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ require_domain gate holds (fail-closed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
