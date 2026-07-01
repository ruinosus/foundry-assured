"""The /platform-hosted Invocations bridge emits a well-formed AG-UI SSE envelope and,
when the hosted agent is unreachable/undeployed (no endpoint configured), surfaces a clean
RunErrorEvent instead of crashing. Infra-free — no deployed agent, no network that resolves.

    uv run python -m eval.platform_hosted_bridge_test
"""

from __future__ import annotations

import asyncio
import sys

from app.services.hosted import stream_platform_agui


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    async def collect() -> list[str]:
        out: list[str] = []
        async for chunk in stream_platform_agui({"messages": [{"role": "user", "content": "hi"}]}):
            out.append(chunk)
        return out

    chunks = asyncio.run(collect())
    blob = "".join(chunks)
    check("emits a RUN_STARTED", "RUN_STARTED" in blob or "RunStarted" in blob)
    check("emits a terminal RUN_FINISHED or RUN_ERROR",
          any(t in blob for t in ("RUN_FINISHED", "RUN_ERROR", "RunFinished", "RunError")))
    check("terminal is RUN_ERROR (skeleton, not a real stream)",
          "RUN_ERROR" in blob or "RunError" in blob)

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ platform-hosted bridge emits a clean AG-UI envelope (infra-free).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
