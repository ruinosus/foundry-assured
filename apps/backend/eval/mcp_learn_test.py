"""End-to-end proof: the platform agent answers a Microsoft-docs question via the PUBLIC
Learn MCP server — no OBO, no azd. The spec's infra-free gate ("run it, don't claim it").

Needs only a Foundry model (FOUNDRY_PROJECT_ENDPOINT + DefaultAzureCredential) and outbound
HTTPS to learn.microsoft.com. Auth is OFF locally, so the role filter degrades open and the
Learn read tools are visible.

    MCP_ENABLED=1 uv run python -m eval.mcp_learn_test
"""

from __future__ import annotations

import asyncio
import sys

from app.agents.platform import build_platform_agent, platform_configured


async def _run() -> int:
    if not platform_configured():
        print("✗ platform not configured (set MCP_ENABLED=1 and FOUNDRY_PROJECT_ENDPOINT).")
        return 1
    agent = build_platform_agent()
    reply = await agent.run(
        "Using the Microsoft Learn docs, what is Azure AI Foundry Agent Service? "
        "Cite the doc you used."
    )
    text = reply.text  # AgentResponse.text — repo convention (eval/run_eval.py)
    print("---- agent reply ----")
    print(text[:800])
    print("---------------------")
    ok = len(text) > 0 and ("learn.microsoft.com" in text.lower() or "foundry" in text.lower())
    print(f"  {'✓' if ok else '✗'} grounded answer with a Learn reference")
    if not ok:
        print("\n❌ Learn MCP did not produce a grounded answer.")
        return 1
    print("\n✅ Learn MCP end-to-end: the platform agent answered from the docs.")
    return 0


def main() -> int:
    return asyncio.run(_run())


if __name__ == "__main__":
    sys.exit(main())
