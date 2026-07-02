"""Shared mode boots: importing app.main under DEPLOYMENT_MODE=shared + auth + the in-memory
tenant store must NOT raise (the gap this sub-project closes). Infra-free — the memory store
backend means no Azure is touched at boot.

    uv run python -m eval.shared_boot_smoke_test
"""

from __future__ import annotations

import importlib
import os
import sys


def main() -> int:
    os.environ["DEPLOYMENT_MODE"] = "shared"
    os.environ["TENANT_STORE_BACKEND"] = "memory"
    # auth_enabled is a derived property: bool(entra_tenant_id and entra_api_client_id).
    # Set BOTH real fields so settings.auth_enabled becomes True and shared+auth boots.
    os.environ.setdefault("ENTRA_TENANT_ID", "00000000-0000-0000-0000-000000000000")
    os.environ.setdefault("ENTRA_API_CLIENT_ID", "00000000-0000-0000-0000-000000000000")

    failures: list[str] = []
    try:
        for m in [k for k in list(sys.modules) if k.startswith("app.")]:
            del sys.modules[m]
        main_mod = importlib.import_module("app.main")
        ok = hasattr(main_mod, "app")
        print(f"  {'✓' if ok else '✗'} app.main imported under shared mode")
        if not ok:
            failures.append("app object missing")
    except Exception as exc:  # noqa: BLE001
        print(f"  ✗ import raised: {type(exc).__name__}: {exc}")
        failures.append("import raised")

    if failures:
        print("\n❌ shared boot failed.")
        return 1
    print("\n✅ shared mode boots clean (no tenant_config at boot).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
