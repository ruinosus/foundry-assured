"""*_configured() are mode-aware: shared returns True WITHOUT reading tenant_config();
self-hosted reads config exactly as before. The shared path is what lets the app boot
before any tenant is resolved.

Infra-free — flips settings.deployment_mode and asserts the shared return values WHILE
each agent module's tenant_config is patched to a landmine that raises. So the test proves
the load-bearing property (shared short-circuits without reading a tenant) regardless of
.env state, not just that the return values happen to be right.

    uv run python -m eval.configured_mode_test
"""

from __future__ import annotations

import sys

from app.shared.settings import settings


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    import app.modules.grounded.internal.concierge as _con
    import app.modules.grounded.internal.cockpit as _cok
    import app.modules.grounded.internal.selfwiki as _sw
    import app.modules.platform_ops.internal.platform as _plat

    from app.modules.grounded.internal.concierge import _knowledge_configured
    from app.modules.grounded.internal.cockpit import cockpit_configured
    from app.modules.grounded.internal.selfwiki import selfwiki_configured
    from app.modules.platform_ops.internal.platform import platform_configured

    def _boom():
        raise RuntimeError("tenant_config() must not be called in shared mode at boot")

    # The agents do `from app.core.tenant import tenant_config`, so each module holds its
    # OWN reference in its namespace — patch THOSE (not app.core.tenant). With the landmine
    # armed, if any *_configured() in shared mode falls through to tenant_config(), _boom()
    # raises and this test ERRORS. That makes the test guard the load-bearing property
    # (shared never reads a tenant) independently of .env state, not just the return values.
    _mods = (_con, _cok, _sw, _plat)

    orig_mode = settings.deployment_mode
    orig_mcp = settings.mcp_enabled
    _orig_tc = [m.tenant_config for m in _mods]
    try:
        settings.deployment_mode = "shared"
        settings.mcp_enabled = True
        for m in _mods:
            m.tenant_config = _boom
        check("shared: _knowledge_configured True", _knowledge_configured() is True)
        check("shared: cockpit_configured True", cockpit_configured() is True)
        check("shared: selfwiki_configured True", selfwiki_configured() is True)
        check("shared: platform_configured True when mcp on", platform_configured() is True)

        settings.mcp_enabled = False
        check("shared: platform_configured False when mcp off", platform_configured() is False)
    finally:
        settings.deployment_mode = orig_mode
        settings.mcp_enabled = orig_mcp
        for m, tc in zip(_mods, _orig_tc):
            m.tenant_config = tc

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ *_configured() are mode-aware (shared boots without a tenant).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
