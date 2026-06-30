"""*_configured() are mode-aware: shared returns True WITHOUT reading tenant_config();
self-hosted reads config exactly as before. The shared path is what lets the app boot
before any tenant is resolved.

Infra-free — flips settings.deployment_mode and asserts the shared return values.

    uv run python -m eval.configured_mode_test
"""

from __future__ import annotations

import sys

from app.core.settings import settings


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    from app.agents.concierge import _knowledge_configured
    from app.agents.cockpit import cockpit_configured
    from app.agents.selfwiki import selfwiki_configured
    from app.agents.platform import platform_configured

    orig_mode = settings.deployment_mode
    orig_mcp = settings.mcp_enabled
    try:
        settings.deployment_mode = "shared"
        settings.mcp_enabled = True
        check("shared: _knowledge_configured True", _knowledge_configured() is True)
        check("shared: cockpit_configured True", cockpit_configured() is True)
        check("shared: selfwiki_configured True", selfwiki_configured() is True)
        check("shared: platform_configured True when mcp on", platform_configured() is True)

        settings.mcp_enabled = False
        check("shared: platform_configured False when mcp off", platform_configured() is False)
    finally:
        settings.deployment_mode = orig_mode
        settings.mcp_enabled = orig_mcp

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ *_configured() are mode-aware (shared boots without a tenant).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
