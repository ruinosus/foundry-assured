# Hosted-agent entrypoint — Project wiki (selfwiki) expert.
#
# Packages the selfwiki expert as a Foundry *hosted agent*: a container that serves
# the Responses protocol on port 8088, invoked through the Foundry gateway. Mirrors
# apps/hosted-cockpit/main.py — a self-contained, single-identity variant of the live
# /selfwiki agent (app/agents/selfwiki.py), grounded in the selfwiki-kb deep-wiki
# (agentic retrieval). Config from env (agent.yaml); auth via the platform-injected
# agent identity (DefaultAzureCredential). Pure grounded Q&A — no workflow/memory/HITL.
#
# Why hosted: the container managed identity CAN invoke hosted agents but 403s on raw
# model inference, so this is the keyless path that actually answers. Instructions mirror
# app/agents/prompts.SELFWIKI_INSTRUCTIONS — keep in sync.

import asyncio
import os

from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Composed from the declarative DNA scope (apps/backend/.dna/helpdesk, agent
# `selfwiki`) — the single source of truth, no inline byte-copy here (ADR-013).
from prompts import SELFWIKI_INSTRUCTIONS

load_dotenv()


async def main() -> None:
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # Foundry IQ knowledge base (agentic) — the same selfwiki-kb the live app grounds in.
    search = AzureAISearchContextProvider(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        knowledge_base_name=os.environ["AZURE_SEARCH_KNOWLEDGE_BASE"],
        credential=credential,
        mode="agentic",
        retrieval_reasoning_effort="medium",
    )

    async with search:
        agent = client.as_agent(
            name="SelfwikiExpert",
            description="foundry-assured project expert grounded in the repo's deep-wiki.",
            instructions=SELFWIKI_INSTRUCTIONS,
            context_providers=[search],
            default_options={"store": False},
        )

        server = ResponsesHostServer(agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
