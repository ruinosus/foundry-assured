"""Unit test for the MCP registry's pure role→visible-tools logic (infra-free).

No network, no framework — asserts the data + the access rules the spec defines:
read needs Reader+, write needs Author/Admin, unclassified tools fail closed (write),
and only m365 is disabled.

    uv run python -m eval.mcp_registry_test
"""

from __future__ import annotations

import sys

from app.agents.mcp.registry import (
    SERVERS,
    classify_tool,
    get_server,
    visible_tools,
)


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # Registry shape
    ids = {s.id for s in SERVERS}
    check("all six servers present",
          ids == {"learn", "azure", "entra", "azdo", "github", "m365"})
    check("learn is public + read-only + enabled",
          get_server("learn").auth == "public"
          and not get_server("learn").write_tools
          and get_server("learn").enabled)
    # azure/entra have no remote endpoint, m365 is Frontier-gated → all disabled. learn/azdo/
    # github have real endpoints (azdo/github gated by config in the builder, not the registry).
    check("disabled set = azure, entra, m365",
          {s.id for s in SERVERS if not s.enabled} == {"azure", "entra", "m365"})
    check("github auth is github_pat (NOT obo)",
          get_server("github").auth == "github_pat")
    check("azdo url is the real templated remote endpoint",
          get_server("azdo").url == "https://mcp.dev.azure.com/{org}")

    azure = get_server("azure")
    # classify_tool: read/write/unknown, fail-closed
    check("a declared read tool classifies read",
          classify_tool(azure, azure.read_tools[0]) == "read")
    check("a declared write tool classifies write",
          classify_tool(azure, azure.write_tools[0]) == "write")
    check("an UNDECLARED tool fails closed to write",
          classify_tool(azure, "azure_totally_new_tool") == "write")

    # visible_tools: role gating
    reader = {"Reader"}
    author = {"Author"}
    none: set[str] = set()
    r_reads, r_writes = visible_tools(azure, reader)
    check("Reader sees azure reads", r_reads == list(azure.read_tools))
    check("Reader sees NO azure writes", r_writes == [])
    a_reads, a_writes = visible_tools(azure, author)
    check("Author sees azure writes", a_writes == list(azure.write_tools))
    check("Author also sees azure reads", a_reads == list(azure.read_tools))
    n_reads, n_writes = visible_tools(azure, none)
    check("no-role caller sees nothing", n_reads == [] and n_writes == [])

    if failures:
        print(f"\n❌ {len(failures)} registry assertion(s) failed.")
        return 1
    print("\n✅ MCP registry logic holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
