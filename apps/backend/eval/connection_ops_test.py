"""Pure connection ops: validate_kind against the registry catalog; add/remove returns a new
TenantRecord (frozen, immutable). Infra-free.

    uv run python -m eval.connection_ops_test
"""

from __future__ import annotations

import sys

from app.core.tenant import TenantConfig
from app.core.tenant_store import (
    Connection, TenantRecord, validate_kind, with_connection, without_connection,
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    check("a real registry id validates", validate_kind("github") and validate_kind("azdo"))
    check("a bogus kind is rejected", not validate_kind("not_a_server") and not validate_kind("mcp_github"))

    rec = TenantRecord(tid="t1", name="Acme", tier="shared", status="active",
                       data_plane=TenantConfig())
    c1 = Connection(id="c1", kind="github", label="GH")
    rec2 = with_connection(rec, c1)
    check("with_connection adds it", rec2.connections == (c1,))
    check("original record is unchanged (frozen)", rec.connections == ())

    # upsert: same id replaces, doesn't duplicate
    c1b = Connection(id="c1", kind="github", label="GH-renamed")
    rec2b = with_connection(rec2, c1b)
    check("with_connection upserts by id (no dup)", rec2b.connections == (c1b,))

    rec3 = without_connection(rec2, "c1")
    check("without_connection removes it", rec3.connections == ())

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ connection ops hold.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
