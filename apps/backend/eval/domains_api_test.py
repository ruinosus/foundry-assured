"""onboard() seeds enabled_domains=DOMAIN_IDS; GET/PUT /tenant/domains read & tighten it,
tenant-scoped, rejecting unknown ids. Infra-free — drives the route functions with a fake
store + a stubbed current_tenant_id (no Entra, no network).

    uv run python -m eval.domains_api_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from fastapi import HTTPException

from app.core import auth as _auth
import app.api.tenant as tapi
from app.core.tenant import DOMAIN_IDS
from app.core.tenant_store import InMemoryTenantStore


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    store = InMemoryTenantStore()
    _auth._tenant_store = store
    tapi.current_tenant_id = lambda: "t-1"  # type: ignore[assignment]  # stub the resolved tenant

    tapi.onboard(SimpleNamespace(tid="t-1"))
    rec = store.get("t-1")
    check("onboard seeds enabled_domains=DOMAIN_IDS", rec.enabled_domains == DOMAIN_IDS)

    got = tapi.get_domains()
    check("GET catalog == DOMAIN_IDS", tuple(got["catalog"]) == DOMAIN_IDS)
    check("GET enabled == DOMAIN_IDS", tuple(got["enabled"]) == DOMAIN_IDS)

    tapi.put_domains(tapi.DomainsBody(enabled=["helpdesk", "platform"]))
    check("PUT tightens enabled", store.get("t-1").enabled_domains == ("helpdesk", "platform"))

    def rejects_unknown() -> bool:
        try:
            tapi.put_domains(tapi.DomainsBody(enabled=["helpdesk", "bogus"]))
            return False
        except HTTPException as e:
            return e.status_code in (400, 422)

    check("PUT rejects unknown domain id", rejects_unknown())
    check("rejected PUT did not mutate", store.get("t-1").enabled_domains == ("helpdesk", "platform"))

    _auth._tenant_store = None
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ domains API: seed + read + tighten + reject-unknown, tenant-scoped.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
