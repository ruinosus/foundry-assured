# Hosted-agent entrypoint (Phase 6).
#
# Packages the helpdesk workflow (triage -> retrieve -> resolve) as a Foundry
# *hosted agent*: a container that serves the Responses protocol on port 8088,
# invoked through the Foundry gateway. agent-framework-foundry-hosting's
# ResponsesHostServer is the bridge — it serves any agent (here a workflow wrapped
# as an agent) over /responses.
#
# This is a deliberately self-contained, single-identity variant of the live app's
# workflow (app/workflow/*): it grounds in the same Foundry IQ knowledge base but
# drops OBO, per-user memory and the human-in-the-loop escalation — those run as
# the signed-in user in the AG-UI app and don't fit the hosted single-identity,
# request/response model. Auth is the platform-injected agent identity via
# DefaultAzureCredential; config comes from env (declared in agent.yaml or injected
# by the platform). Mirrors the official samples responses/05_workflows and
# 08_azure_search_rag. APIs verified against agent-framework 1.9.0.

import asyncio
import os

from agent_framework import AgentExecutor, WorkflowBuilder
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from agent_framework_foundry_hosting import ResponsesHostServer
from azure.identity import DefaultAzureCredential
from dotenv import load_dotenv

# Prompts are composed from the declarative DNA scope (apps/backend/.dna/helpdesk),
# the single source of truth — no inline byte-copies here (ADR-013). RESOLVE uses
# the resolve-hosted variant (no TICKET/HITL escalation; hosted is single-identity).
from prompts import RESOLVE_INSTRUCTIONS, RETRIEVE_INSTRUCTIONS, TRIAGE_INSTRUCTIONS

load_dotenv()


async def main() -> None:
    credential = DefaultAzureCredential()

    client = FoundryChatClient(
        project_endpoint=os.environ["FOUNDRY_PROJECT_ENDPOINT"],
        model=os.environ["AZURE_AI_MODEL_DEPLOYMENT_NAME"],
        credential=credential,
    )

    # Foundry IQ knowledge base, agentic retrieval — same KB the live app grounds in.
    search = AzureAISearchContextProvider(
        endpoint=os.environ["AZURE_SEARCH_ENDPOINT"],
        knowledge_base_name=os.environ["AZURE_SEARCH_KNOWLEDGE_BASE"],
        credential=credential,
        mode="agentic",
    )

    async with search:
        # context_mode="last_agent": each step sees only the previous step's output,
        # matching the live pipeline (triage -> retrieve -> resolve).
        triage = AgentExecutor(
            client.as_agent(name="triage", instructions=TRIAGE_INSTRUCTIONS),
            context_mode="last_agent",
        )
        retrieve = AgentExecutor(
            client.as_agent(
                name="retrieve",
                instructions=RETRIEVE_INSTRUCTIONS,
                context_providers=[search],
            ),
            context_mode="last_agent",
        )
        resolve = AgentExecutor(
            client.as_agent(
                name="resolve",
                instructions=RESOLVE_INSTRUCTIONS,
                # Foundry hosting manages conversation history; don't double-store.
                default_options={"store": False},
            ),
            context_mode="last_agent",
        )

        workflow_agent = (
            WorkflowBuilder(
                name="HelpdeskConcierge",
                start_executor=triage,
                output_from=[resolve],  # only the resolved answer is the agent's output
            )
            .add_edge(triage, retrieve)
            .add_edge(retrieve, resolve)
            .build()
            .as_agent()
        )

        server = ResponsesHostServer(workflow_agent)
        await server.run_async()


if __name__ == "__main__":
    asyncio.run(main())
