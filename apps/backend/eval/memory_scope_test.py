"""memory_scope: bare in single-tenant (no orphaned memories), tid-prefixed in multi-tenant.

Drives the two contextvars directly — no store, no network.

    uv run python -m eval.memory_scope_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from app.core import auth
from app.core.tenant import set_current_tenant


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # Single-tenant: a user, no tenant set → bare oid (today's behavior).
    auth._current_user.set(SimpleNamespace(oid="user-123", roles=[]))
    set_current_tenant(None)
    check("single-tenant scope is bare oid", auth.memory_scope() == "user-123")

    # Multi-tenant: a resolved tenant with a tid → prefixed.
    set_current_tenant(SimpleNamespace(tid="tenant-abc"))
    check("multi-tenant scope is tid:oid", auth.memory_scope() == "tenant-abc:user-123")

    # No user at all → dev-local (auth-off path), still works.
    auth._current_user.set(None)
    set_current_tenant(None)
    check("no user → dev-local", auth.memory_scope() == "dev-local")

    set_current_tenant(None)
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ memory_scope guard holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
