"""Helpdesk concierge agent.

Phase 0: a plain concierge backed by the Foundry model.
Phase 1: when a Foundry IQ knowledge base is configured, attach an
AzureAISearchContextProvider in agentic mode so the agent grounds its answers in
the runbook corpus and cites sources (and says "I don't know" off-corpus).

If the knowledge base settings are absent (not yet provisioned/ingested), the
agent falls back to the Phase 0 behavior so the app still boots.

APIs verified against agent-framework 1.9.0 / agent-framework-azure-ai-search.
"""

from agent_framework import Agent
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from app.agents.prompts import (
    CONCIERGE_GROUNDED_INSTRUCTIONS,
    CONCIERGE_UNGROUNDED_INSTRUCTIONS,
)
from app.core.settings import settings


def _knowledge_configured() -> bool:
    return bool(settings.azure_search_endpoint and settings.azure_search_knowledge_base)


def build_concierge_agent() -> Agent:
    """Create the concierge, grounding it in the knowledge base when available."""
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint or None,
        model=settings.foundry_model,
        credential=credential,
    )

    if _knowledge_configured():
        search = AzureAISearchContextProvider(
            endpoint=settings.azure_search_endpoint,
            knowledge_base_name=settings.azure_search_knowledge_base,
            credential=credential,
            mode="agentic",
        )
        return client.as_agent(
            name="HelpdeskConcierge",
            description="Internal engineering support concierge grounded in runbooks.",
            instructions=CONCIERGE_GROUNDED_INSTRUCTIONS,
            context_providers=[search],
        )

    return client.as_agent(
        name="HelpdeskConcierge",
        description="Internal engineering support concierge (no KB configured).",
        instructions=CONCIERGE_UNGROUNDED_INSTRUCTIONS,
    )
