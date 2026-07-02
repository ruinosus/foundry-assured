"""Per-tool RBAC: stricter-of-both (registry min-role AND Connection min-role). Infra-free.

    uv run python -m eval.rbac_per_tool_test
"""

from __future__ import annotations

import sys

from app.agents.mcp.registry import get_server, server_for_kind, visible_tools_for
from app.core.tenant_store import Connection


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    azdo = get_server("azdo")
    base = Connection(id="c", kind="azdo", label="ADO")

    r_reads, r_writes = visible_tools_for(azdo, base, {"Reader"})
    check("Reader sees azdo reads", r_reads == list(azdo.read_tools))
    check("Reader sees NO writes", r_writes == [])

    _, a_writes = visible_tools_for(azdo, base, {"Author"})
    check("Author sees azdo writes", a_writes == list(azdo.write_tools))

    tight = Connection(id="c", kind="azdo", label="ADO", min_role_read="Author")
    t_reads, _ = visible_tools_for(azdo, tight, {"Reader"})
    check("Connection tightening hides reads from Reader", t_reads == [])
    t_reads2, _ = visible_tools_for(azdo, tight, {"Author"})
    check("Author still sees tightened reads", t_reads2 == list(azdo.read_tools))

    check("server_for_kind resolves a real id", server_for_kind("github").id == "github")
    check("server_for_kind unknown -> None", server_for_kind("nope") is None)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ per-tool RBAC holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
