"""build_artifact_mcp_reads: read-only + mcp_enabled gate (no network).

Run (from apps/backend/):  uv run python -m eval.artifact_mcp_reads_test
"""
import sys


def main() -> int:
    failures: list[str] = []

    def check(name, cond):
        print(f"{'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    import app.core.settings as settings_mod
    from app.agents.mcp import tools as mcp_tools

    # Gate: off by default → no tools.
    settings_mod.settings.mcp_enabled = False
    check("returns [] when MCP disabled", mcp_tools.build_artifact_mcp_reads() == [])

    # Enabled → tools built, and NONE expose a write tool name (read-only).
    settings_mod.settings.mcp_enabled = True
    from app.agents.mcp.registry import enabled_servers
    write_names = {w for s in enabled_servers() for w in s.write_tools}
    built = mcp_tools.build_artifact_mcp_reads()
    check("builds at least one read tool when enabled (learn is public)", len(built) >= 1)
    exposed = {t for tool in built for t in getattr(tool, "allowed_tools", [])}
    check("no write tools exposed", not (exposed & write_names))
    settings_mod.settings.mcp_enabled = False  # restore

    print("PASS" if not failures else f"FAIL ({len(failures)})")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
