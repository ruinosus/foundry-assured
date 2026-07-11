# Hosted-agent entrypoint — Cockpit expert (Phase C, second domain).
#
# Packages the Cockpit expert as a Foundry *hosted agent*: a container that serves
# the Responses protocol on port 8088, invoked through the Foundry gateway.
# agent-framework-foundry-hosting's ResponsesHostServer is the bridge.
#
# A self-contained, single-identity variant of the live /cockpit agent
# (app/agents/cockpit.py): same Foundry IQ knowledge base (cockpit-kb, agentic
# retrieval) grounding, but config comes from env (declared in agent.yaml / injected
# by the platform) and auth is the platform-injected agent identity via
# DefaultAzureCredential. Pure grounded Q&A — no workflow, memory or HITL.
# APIs mirror app/agents/cockpit.py; verified against agent-framework 1.9.0.

import asyncio
import os

from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Composed from the declarative DNA scope (apps/backend/.dna/helpdesk, agent
# `cockpit`) — the single source of truth, no inline byte-copy here (ADR-013).
from prompts import COCKPIT_INSTRUCTIONS

load_dotenv()


async def main() -> None:
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # Foundry IQ knowledge base (agentic) — the same cockpit-kb the live app grounds in.
    # reasoning_effort="medium" = iterative query planning for retrieval completeness
    # (Phase 2); mirrors app/agents/cockpit.py.
    search = AzureAISearchContextProvider(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        knowledge_base_name=os.environ["AZURE_SEARCH_KNOWLEDGE_BASE"],
        credential=credential,
        mode="agentic",
        retrieval_reasoning_effort="medium",
    )

    async with search:
        agent = client.as_agent(
            name="CockpitExpert",
            description="Avanade Cockpit platform expert grounded in the Cockpit knowledge base.",
            instructions=COCKPIT_INSTRUCTIONS,
            context_providers=[search],
            # Foundry hosting manages conversation history; don't double-store.
            default_options={"store": False},
        )

        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
