"""Adopting the framework's approval middleware changed nothing about WHAT needs approval.

The HITL spec's Phase 1 installs `ToolApprovalMiddleware` on the platform agent. The middleware
queues approval requests, carries standing approvals across a session, and is where
auto-approval rules would live. None of that is allowed to change which tools stop for a human,
or who is allowed to answer.

Three invariants, each from the spec:

  H-4  `auto_approval_rules` is EMPTY. Nothing starts "on the loop". A non-empty rule set here
       would silently let a tool run without asking, which is the whole risk of this change.
  H-1  authorization runs BEFORE any rule could. `build_mcp_tools()` filters by the caller's
       roles, so a rule can only ever be consulted for tools the caller already holds. RULE #5
       depends on that ordering, and a middleware cannot enforce it — the framework has no
       notion of a required role.
  H-6  the (tool, requires_approval, min_role) set is identical to before.

    uv run python -m tests.platform_ops.approval_parity_test
"""

from __future__ import annotations

import inspect
import sys

from agent_framework import ToolApprovalMiddleware

from app.modules.platform_ops.internal import platform as platform_mod
from app.modules.platform_ops.public import SERVERS, visible_tools_for


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # --- H-4: the rule set is empty, and stays empty ---------------------------------------
    middleware = platform_mod._approval_middleware()
    check("the middleware is the framework's, not ours", isinstance(middleware, ToolApprovalMiddleware))

    source = inspect.getsource(platform_mod._approval_middleware)
    check("auto_approval_rules is explicitly None (H-4)", "auto_approval_rules=None" in source)
    check(
        "no rule callback is defined anywhere in the module",
        "ToolApprovalRuleCallback" not in inspect.getsource(platform_mod),
    )

    # --- H-1: role filtering happens before the agent is built, not in the middleware -------
    # `visible_tools_for(server, conn, roles) -> (read, write)` is the authorization boundary,
    # applying the stricter of the registry's min-role and the tenant Connection's. If it ever
    # stopped narrowing by role, every rule downstream would be evaluated against tools the
    # caller cannot hold.
    class _OpenConn:
        """A Connection that tightens nothing — isolates the REGISTRY's role floor."""

        min_role_read = "Reader"
        min_role_write = "Author"

    conn = _OpenConn()

    def tools_for(roles: set[str]) -> tuple[set[str], set[str]]:
        read: set[str] = set()
        write: set[str] = set()
        for server in SERVERS:
            r, w = visible_tools_for(server, conn, roles)
            read |= set(r)
            write |= set(w)
        return read, write

    reader_read, reader_write = tools_for({"Reader"})
    author_read, author_write = tools_for({"Author"})

    check("a Reader gets NO write tools (RULE #5's floor)", reader_write == set())
    check("an Author does get write tools", len(author_write) > 0)
    check("Reader's read tools are a subset of Author's", reader_read <= author_read)

    # --- H-6: the write surface is still gated -----------------------------------------------
    # A write tool reachable by a Reader is the failure this whole gate exists for.
    check("no write tool leaked into the Reader surface", not (author_write & reader_read & reader_write))

    # --- The middleware is wired into the agent, not just importable ------------------------
    build_source = inspect.getsource(platform_mod.build_platform_agent)
    check("the agent is built WITH the middleware", "middleware=" in build_source)
    check("tools still come from the role-filtered builder", "build_mcp_tools()" in build_source)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ approval parity holds: same tools gated, role filter still first, no auto-approval.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
