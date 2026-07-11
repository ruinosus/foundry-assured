"""Smoke test: the shared-mode MultiTenant scheme constructs (validate_iss requires iss_callable)
and the issuer callable is correct. Infra-free — does NOT build the store or hit Entra.

    uv run python -m eval.multitenant_scheme_test
"""

from __future__ import annotations

import sys

from fastapi_azure_auth import MultiTenantAzureAuthorizationCodeBearer

from app.core.auth import _iss_callable


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    check("iss_callable returns the per-tenant issuer",
          _iss_callable("t-123") == "https://login.microsoftonline.com/t-123/v2.0")

    # The regression that slipped: validate_iss=True must construct (it raises without iss_callable).
    try:
        MultiTenantAzureAuthorizationCodeBearer(
            app_client_id="00000000-0000-0000-0000-000000000000",
            scopes={"api://x/access_as_user": "access_as_user"},
            validate_iss=True,
            iss_callable=_iss_callable,
            allow_guest_users=True,
        )
        constructed = True
    except Exception as exc:  # noqa: BLE001
        print(f"    scheme construction raised: {type(exc).__name__}: {exc}")
        constructed = False
    check("shared-mode MultiTenant scheme constructs with validate_iss", constructed)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ multitenant scheme smoke test holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
