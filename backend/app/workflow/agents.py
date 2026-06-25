"""The three workflow agents: triage -> retrieve -> resolve.

Each agent is a Foundry-backed ChatAgent. Their `name` becomes the workflow
executor id, which the AG-UI adapter emits as the step name the frontend renders
(verified: resolve_agent_id falls back to agent.name). So names are lowercase,
UI-facing: "triage", "retrieve", "resolve".

The chain passes each agent's output to the next, so instructions are written so
every step's output is self-contained for the step that follows.
"""

from agent_framework import Agent
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from azure.core.credentials import TokenCredential

from app.settings import settings


def _client(credential: TokenCredential) -> FoundryChatClient:
    return FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint or None,
        model=settings.foundry_model,
        credential=credential,
    )


TRIAGE_INSTRUCTIONS = (
    "You are the TRIAGE step of a helpdesk workflow. Do NOT answer the question. "
    "Classify the developer's request and restate it for the next step. Output exactly:\n"
    "Intent: <one short phrase>\n"
    "Urgency: <low|medium|high>\n"
    "Restated: <the question in one clear sentence>"
)


def build_triage_agent(credential: TokenCredential) -> Agent:
    return _client(credential).as_agent(
        name="triage",
        description="Classifies intent and urgency, restates the question.",
        instructions=TRIAGE_INSTRUCTIONS,
    )


RETRIEVE_INSTRUCTIONS = (
    "You are the RETRIEVE step of a helpdesk workflow. Using the runbook knowledge "
    "base, find the passages relevant to the triaged question. Do NOT write the final "
    "answer. Output the relevant runbook content followed by the exact source document "
    "titles you used. If nothing relevant is found, output exactly 'NO_MATCH'."
)


def build_retrieve_agent(credential: TokenCredential) -> Agent:
    search = AzureAISearchContextProvider(
        endpoint=settings.azure_search_endpoint,
        knowledge_base_name=settings.azure_search_knowledge_base,
        credential=credential,
        mode="agentic",
    )
    return _client(credential).as_agent(
        name="retrieve",
        description="Retrieves grounding passages + sources from the knowledge base.",
        instructions=RETRIEVE_INSTRUCTIONS,
        context_providers=[search],
    )


RESOLVE_INSTRUCTIONS = (
    "You are the RESOLVE step of a helpdesk workflow. Write the final answer to the "
    "developer, grounded ONLY in the runbook content the RETRIEVE step provided. Cite "
    "the source document title(s) for every claim. If the retrieve step returned "
    "'NO_MATCH' or nothing relevant, say you don't know instead of guessing — never "
    "invent runbooks, sources, or steps. Use the developer's remembered preferences "
    "(e.g. their OS or stack) to tailor the steps when relevant."
)


def build_resolve_agent(
    credential: TokenCredential, context_providers: list | None = None
) -> Agent:
    # The memory provider (when present) is attached here so it reads the dev's
    # preferences/past resolutions before resolving and stores the resolution after.
    return _client(credential).as_agent(
        name="resolve",
        description="Writes the final grounded, cited answer.",
        instructions=RESOLVE_INSTRUCTIONS,
        context_providers=context_providers or None,
    )
