"""Local MCP connectivity test — the plumbing, with ZERO Azure infra.

Unlike eval/mcp_learn_test.py (which drives the agent and needs a Foundry model), this just
connects to the live MCP servers and lists the tools they expose — no Foundry, no auth, only
outbound HTTPS. It proves our MCPStreamableHTTPTool wiring + allowed_tools filtering work end
to end against the real servers, on a laptop.

  - Learn (public): always runs.
  - GitHub: runs only if MCP_GITHUB_PAT is set (GitHub's own OAuth, not Entra OBO).

    uv run python -m eval.mcp_connect_test
"""

from __future__ import annotations

import asyncio
import os
import sys

from agent_framework import MCPStreamableHTTPTool


def _tool_names(tool: MCPStreamableHTTPTool) -> list[str]:
    fns = getattr(tool, "functions", None) or getattr(tool, "_functions", None) or []
    return [getattr(f, "name", str(f)) for f in fns]


async def _check_server(label: str, **kwargs) -> tuple[str, list[str]]:
    async with MCPStreamableHTTPTool(**kwargs) as tool:
        return label, _tool_names(tool)


async def _run() -> int:
    failures: list[str] = []

    # Learn — public, always.
    label, names = await _check_server(
        "Learn",
        name="learn",
        url="https://learn.microsoft.com/api/mcp",
        allowed_tools=["microsoft_docs_search", "microsoft_docs_fetch"],
    )
    ok = "microsoft_docs_search" in names
    print(f"  {'✓' if ok else '✗'} {label}: connected, tools = {names}")
    if not ok:
        failures.append(label)

    # GitHub — only if a PAT is configured.
    pat = os.environ.get("MCP_GITHUB_PAT")
    if pat:
        try:
            label, names = await _check_server(
                "GitHub",
                name="github",
                url="https://api.githubcopilot.com/mcp/",
                header_provider=lambda _existing: {"Authorization": f"Bearer {pat}"},
            )
            ok = len(names) > 0
            print(f"  {'✓' if ok else '✗'} {label}: connected, {len(names)} tools")
            if not ok:
                failures.append(label)
        except Exception as exc:  # noqa: BLE001 — surface the auth/transport error plainly
            print(f"  ✗ GitHub: {type(exc).__name__}: {exc}")
            failures.append("GitHub")
    else:
        print("  – GitHub: skipped (set MCP_GITHUB_PAT to test it)")

    if failures:
        print(f"\n❌ {len(failures)} server(s) failed to connect.")
        return 1
    print("\n✅ MCP connectivity OK (no Azure infra needed).")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
