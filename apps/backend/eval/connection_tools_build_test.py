"""Connection-driven build (shared mode), infra-free: maps Connections → tools, applies per-tool
RBAC. Uses an in-memory store + the public 'learn' server so no network/credential is needed.

    uv run python -m eval.connection_tools_build_test
"""

from __future__ import annotations

import sys

from app.agents.mcp import tools as T
from app.core.tenant import TenantConfig
from app.core.tenant_store import Connection


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    learn = Connection(id="l", kind="learn", label="Learn", enabled=True)

    built = T.build_from_connections((learn,), {"Admin"})
    check("one tool built for the learn connection", len(built) == 1)
    check("disabled connection yields nothing",
          T.build_from_connections((Connection(id="x", kind="learn", label="L", enabled=False),), {"Admin"}) == [])
    check("unknown kind yields nothing",
          T.build_from_connections((Connection(id="x", kind="bogus", label="B"),), {"Admin"}) == [])
    check("a Reader still gets the public read tools",
          len(T.build_from_connections((learn,), {"Reader"})) == 1)
    check("no-role caller gets nothing",
          T.build_from_connections((learn,), set()) == [])

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ connection-driven build holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
