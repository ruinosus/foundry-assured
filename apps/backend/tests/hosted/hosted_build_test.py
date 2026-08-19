"""Hosted builder (infra-free): assembles get_mcp_tool(project_connection_id=...) per connection,
with the per-tool approval dict + RBAC-filtered allowed_tools. Uses a fake get_tool that records
kwargs — no live Foundry.

    uv run python -m eval.hosted_build_test
"""

from __future__ import annotations

import sys

from app.modules.platform_ops.internal import mcp_tools as T
from app.modules.platform_ops.internal.mcp_registry import get_server
from app.modules.tenancy.internal.tenant_store import Connection


def main() -> int:
    failures: list[str] = []
    calls: list[dict] = []

    def fake_get_tool(**kwargs):
        calls.append(kwargs)
        return ("TOOL", kwargs)  # stand-in for a FoundryMCPTool

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    github = get_server("github")
    conn = Connection(id="g", kind="github", label="GH", foundry_connection_id="conn:gh", enabled=True)

    built = T.build_hosted_from_connections((conn,), {"Admin"}, fake_get_tool)
    check("one hosted tool built", len(built) == 1 and len(calls) == 1)
    kw = calls[0]
    check("project_connection_id passed", kw.get("project_connection_id") == "conn:gh")
    check("allowed_tools = visible reads+writes",
          set(kw.get("allowed_tools") or []) == set(github.read_tools) | set(github.write_tools))
    check("approval dict gates writes",
          set((kw.get("approval_mode") or {}).get("always_require_approval") or []) == set(github.write_tools))
    check("disabled connection → no call",
          T.build_hosted_from_connections((Connection(id="x", kind="github", label="x", enabled=False),), {"Admin"}, fake_get_tool) == [])
    check("no-role caller → no call",
          T.build_hosted_from_connections((conn,), set(), fake_get_tool) == [])

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ hosted build holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
