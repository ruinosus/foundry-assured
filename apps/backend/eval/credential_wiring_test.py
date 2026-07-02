"""Credential wiring (infra-free): an OBO connection gets a header_provider; a non-OBO connection
WITH a foundry_connection_id is no longer skipped (gets a header_provider — the SDK-broker); a
non-OBO connection WITHOUT a reference is skipped. The actual credential fetch is infra-gated (the
header_provider is constructed but not called here).

    uv run python -m eval.credential_wiring_test
"""

from __future__ import annotations

import sys

from app.agents.mcp import tools as T
from app.core.tenant_store import Connection


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # OBO server (azdo) → builds with a header_provider (already wired).
    azdo = T.build_from_connections(
        (Connection(id="a", kind="azdo", label="ADO", endpoint="org"),), {"Admin"})
    check("OBO connection builds a tool", len(azdo) == 1)
    check("OBO tool has a header_provider", azdo[0]._header_provider is not None)

    # Non-OBO (github) WITH a foundry_connection_id → builds (SDK-broker), not skipped.
    gh = T.build_from_connections(
        (Connection(id="g", kind="github", label="GH", foundry_connection_id="conn:gh"),), {"Admin"})
    check("non-OBO with foundry_connection_id builds a tool", len(gh) == 1)
    check("...and it has a header_provider", gh and gh[0]._header_provider is not None)

    # Non-OBO (github) WITHOUT any reference → skipped.
    gh0 = T.build_from_connections(
        (Connection(id="g0", kind="github", label="GH"),), {"Admin"})
    check("non-OBO without a reference is skipped", gh0 == [])

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ credential wiring holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
