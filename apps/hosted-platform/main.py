# Hosted-platform entrypoint (D-packaging, Phase 1 — Hosted).
#
# Packages the engineering-platform concierge (the TOOL-driven agent, app/agents/platform.py)
# as a Foundry *hosted agent*: a container that serves the **Invocations** protocol on port
# 8088, invoked through the Foundry gateway. agent-framework-foundry-hosting's
# InvocationsHostServer is the bridge — it serves the agent over the Invocations (raw AG-UI)
# protocol so write-approval interrupts can round-trip on the hosted path (which the Responses
# protocol the grounded twins use cannot do).
#
# This is the FULL-PARITY Invocations twin of the live platform agent — NOT the single-identity
# Responses stripping the grounded hosted-agent/hosted-cockpit do. The grounded twins drop
# OBO/memory/HITL because pure Q&A fits a single-identity request/response model; the platform
# concierge instead keeps its tool capability and its write-approval interrupt, which is exactly
# why it serves Invocations rather than Responses.
#
# Tools are NOT built here per-request (that's the live OBO path, build_mcp_tools()). For a
# hosted agent, tools are configured ON the Foundry Toolbox at DEPLOY time and the agent resolves
# them through the Toolbox referenced by FOUNDRY_TOOLBOX_NAME (ADR-011): OAuth identity passthrough
# is DATA on the Toolbox/connection, never hand-rolled credential code here. Auth is the
# platform-injected agent identity via DefaultAzureCredential; config comes from env (declared in
# agent.yaml / injected by the platform). as_agent(...) is verified against agent-framework 1.9.0.

import asyncio
import os

from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import InvocationsHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

load_dotenv()

# Mirror of app/agents/prompts.PLATFORM_INSTRUCTIONS — keep in sync. The backend package is not
# on the container path, so the constant is inlined rather than imported.
PLATFORM_INSTRUCTIONS = (
    "You are the engineering-platform concierge. You answer using the connected Microsoft tools "
    "(Learn docs, and — when enabled — Azure, Entra, Azure DevOps, GitHub). Prefer a tool over "
    "guessing. Ground factual claims in tool results and say which tool/source you used. If a "
    "tool you'd need isn't available to this user, say so plainly rather than inventing an answer. "
    "For any action that changes state (deploy, create issue, directory change), explain what you "
    "would do and let the approval step handle it — never claim you performed a write."
)


async def main() -> None:
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # The Toolbox the agent resolves its MCP tools through. The concrete tool-attach (which
    # tools, which connections, OAuth identity passthrough) is configured ON the Toolbox at
    # deploy time, referenced here by name only — DATA, per ADR-011 / rule #6.
    toolbox_name = os.environ.get("FOUNDRY_TOOLBOX_NAME", "")  # noqa: F841 (referenced by deploy binding)

    # TODO(infra-gated): bind this agent to the Foundry Toolbox named FOUNDRY_TOOLBOX_NAME so its
    # tools resolve at runtime. The Toolbox<->hosted-agent binding + the per-connection tool config
    # (project_connection_id / connector_id / authorization) are deploy-time facts (runbook); do
    # NOT call build_mcp_tools() (the live per-request OBO path) and do NOT hand-roll credentials.
    agent = client.as_agent(
        name="PlatformConcierge",
        description="Engineering-platform concierge over Microsoft first-party MCP tools.",
        instructions=PLATFORM_INSTRUCTIONS,
        # Foundry hosting manages conversation history; don't double-store.
        default_options={"store": False},
    )

    # TODO(infra-gated): confirm InvocationsHostServer ctor against the deployed image.
    # agent-framework-foundry-hosting is a hosted-image-only dep (not in the backend venv), so its
    # signature is not offline-verified — wrapped by analogy to ResponsesHostServer(agent)
    # (apps/hosted-agent/main.py).
    server = InvocationsHostServer(agent)
    await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
