"""Unit test for the tenant-config seam (infra-free).

SingleTenant returns the .env-built config (= today's values); current_tenant_id() is None
in single-tenant mode so memory_scope stays bare.

    uv run python -m eval.tenant_provider_test
"""

from __future__ import annotations

import os
import sys

from app.core.tenant import (
    SingleTenantConfigProvider,
    TenantConfig,
    current_tenant_id,
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    os.environ["FOUNDRY_MODEL"] = "gpt-5-mini"
    cfg = SingleTenantConfigProvider().current()
    check("SingleTenant returns a TenantConfig", isinstance(cfg, TenantConfig))
    check("reads FOUNDRY_MODEL from env", cfg.foundry_model == "gpt-5-mini")
    check("current_tenant_id() is None in single-tenant mode", current_tenant_id() is None)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ tenant provider (SingleTenant) holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
