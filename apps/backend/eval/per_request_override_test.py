"""PerRequestAgent accepts optional name/description overrides; the platform proxy uses them and
still satisfies SupportsAgentRun. Infra-free.

    uv run python -m eval.per_request_override_test
"""

from __future__ import annotations

import sys

from agent_framework import SupportsAgentRun
from app.agents.per_request import PerRequestAgent


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    a = PerRequestAgent("platform", lambda: None, name="PlatformConcierge", description="desc")
    check("name override applied", a.name == "PlatformConcierge")
    check("description override applied", a.description == "desc")
    check("id is the agent_id", a.id == "platform")
    check("default name falls back to id", PerRequestAgent("cockpit", lambda: None).name == "cockpit")
    check("isinstance SupportsAgentRun", isinstance(a, SupportsAgentRun))

    # the platform module exposes a proxy instance built from the generic class
    from app.agents.platform import platform_agent_proxy  # new export
    check("platform proxy is SupportsAgentRun", isinstance(platform_agent_proxy, SupportsAgentRun))
    check("platform proxy keeps its name", platform_agent_proxy.name == "PlatformConcierge")

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ PerRequestAgent override + platform proxy collapse holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
