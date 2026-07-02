"""apps/hosted-platform is well-formed: agent.yaml declares the Invocations protocol, and
the four scaffold files exist. Infra-free — does NOT import main.py or start the host server.

    uv run python -m eval.hosted_platform_smoke_test
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    root = Path(__file__).resolve().parents[2] / "hosted-platform"
    check("hosted-platform/ exists", root.is_dir())
    for f in ("Dockerfile", "agent.yaml", "main.py", "requirements.txt"):
        check(f"{f} present", (root / f).is_file())

    spec = yaml.safe_load((root / "agent.yaml").read_text())
    check("agent.yaml kind: hosted", spec.get("kind") == "hosted")
    check("agent.yaml name: platform-concierge", spec.get("name") == "platform-concierge")
    protocols = [p.get("protocol") for p in (spec.get("protocols") or [])]
    check("agent.yaml declares the invocations protocol", "invocations" in protocols)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ hosted-platform scaffold well-formed (Invocations).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
