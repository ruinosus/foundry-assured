"""The connection-built tool gates writes via approval_mode (write=always_require_approval,
read=never_require_approval). Infra-free — uses an azdo connection (has read+write tools).

    uv run python -m eval.approval_mode_test
"""

from __future__ import annotations

import sys

from app.agents.mcp.registry import get_server
from app.agents.mcp import tools as T
from app.core.tenant_store import Connection


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    azdo = get_server("azdo")  # read_tools + write_tools, auth=obo, url has {org}
    conn = Connection(id="a", kind="azdo", label="ADO", endpoint="myorg", enabled=True)

    built = T.build_from_connections((conn,), {"Admin"})  # Admin sees reads + writes
    check("azdo tool built (Admin)", len(built) == 1)
    tool = built[0]
    am = tool.approval_mode
    check("approval_mode is the per-tool dict", isinstance(am, dict))
    check("writes require approval", set(am.get("always_require_approval") or []) == set(azdo.write_tools))
    check("reads do NOT require approval", set(am.get("never_require_approval") or []) == set(azdo.read_tools))

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ approval_mode gating holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
