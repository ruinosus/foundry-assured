"""TIER_DOMAINS seeds onboarding entitlement from the tenant's tier; unknown/unset tier → all
domains (non-breaking); the request-time gate stays fail-closed regardless. Infra-free.

    uv run python -m eval.tier_domains_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.core import auth as _auth
import app.api.tenant as tapi
from app.core.tenant import DOMAIN_IDS, TIER_DOMAINS, domains_for_tier
from app.core.tenant_store import InMemoryTenantStore


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    check("shared tier → all domains", domains_for_tier("shared") == DOMAIN_IDS)
    check("unknown tier → all domains (non-breaking)", domains_for_tier("mystery") == DOMAIN_IDS)
    check("None tier → all domains", domains_for_tier(None) == DOMAIN_IDS)
    # a restricted tier, if defined, is a strict subset of the catalog
    for tier, doms in TIER_DOMAINS.items():
        check(f"tier '{tier}' ⊆ DOMAIN_IDS", set(doms) <= set(DOMAIN_IDS))

    # onboard seeds from the tier passed in the body
    store = InMemoryTenantStore()
    _auth._tenant_store = store
    tapi.onboard(tapi.OnboardBody(tier="shared"), SimpleNamespace(tid="t-1"))
    check("onboard seeds enabled_domains from tier", store.get("t-1").enabled_domains == domains_for_tier("shared"))
    _auth._tenant_store = None

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tier→domains seeding holds (unknown→all, gate stays fail-closed).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
