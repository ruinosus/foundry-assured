"""onboarding_guard: Admin + allow-list → ok (sets _current_user); missing either → 403.
Does NOT resolve the tenant (so it works pre-onboarding). Infra-free.

    uv run python -m eval.onboarding_guard_test
"""

from __future__ import annotations

import sys
from types import SimpleNamespace

from fastapi import HTTPException

from app.core import auth, onboarding
from app.core.settings import settings


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    settings.onboarding_allowed_tids = "t-ok"
    admin_ok = SimpleNamespace(tid="t-ok", roles=["Admin"], oid="u1")

    onboarding.onboarding_guard(admin_ok)
    check("Admin + allow-listed passes", auth.current_user() is admin_ok)

    def denies(user) -> bool:
        try:
            onboarding.onboarding_guard(user)
            return False
        except HTTPException as e:
            return e.status_code == 403

    check("non-Admin → 403", denies(SimpleNamespace(tid="t-ok", roles=["Reader"], oid="u")))
    check("Admin but not allow-listed → 403", denies(SimpleNamespace(tid="t-other", roles=["Admin"], oid="u")))
    check("missing tid claim → 403 (not 500)", denies(SimpleNamespace(roles=["Admin"], oid="u")))

    settings.onboarding_allowed_tids = ""
    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ onboarding guard holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
