"""Cockpit expert agent — a second domain alongside the helpdesk.

Same Foundry IQ pattern as the concierge, pointed at the **cockpit-kb** (the Cockpit
platform docs ingested by app/knowledge/ingest_cockpit.py). Pure grounded Q&A — no
workflow steps or ticket escalation; the Cockpit corpus is reference knowledge.

Grounding is Microsoft's documented Foundry IQ pattern: the AzureAISearchContextProvider
(agentic retrieval) injects the relevant Cockpit docs — with citations — into context,
and the answering discipline lives in COCKPIT_INSTRUCTIONS. No consume-side Agent Skill:
the KB *is* the knowledge, so a retrieval-discipline skill (and its read_skill_resource
tool) only added noise. Wiki *generation* still uses the deep-wiki skills.

The Cockpit KB is org-wide (not per-user), so this runs under the app's own identity
(DefaultAzureCredential), not OBO. The /cockpit endpoint still requires sign-in.
"""

from agent_framework import Agent
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from app.agents.prompts import COCKPIT_INSTRUCTIONS
from app.core.settings import settings


def cockpit_configured() -> bool:
    return bool(settings.azure_search_endpoint and settings.cockpit_search_knowledge_base)


def build_cockpit_agent() -> Agent:
    """A grounded expert over the Cockpit knowledge base (Foundry IQ agentic retrieval)."""
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint or None,
        model=settings.foundry_model,
        credential=credential,
    )
    # Agentic retrieval (Foundry IQ KB query planning) — best quality on broad questions.
    # Runs in a context-provider hook (before_run), injecting the retrieved Cockpit docs
    # (with citations) into context; it does NOT emit a model tool call, so multi-turn
    # over AG-UI is clean without any tool-message sanitizing.
    search = AzureAISearchContextProvider(
        endpoint=settings.azure_search_endpoint,
        knowledge_base_name=settings.cockpit_search_knowledge_base,
        credential=credential,
        mode="agentic",
    )
    return client.as_agent(
        name="CockpitExpert",
        description="Avanade Cockpit platform expert grounded in the Cockpit knowledge base.",
        instructions=COCKPIT_INSTRUCTIONS,
        context_providers=[search],
    )
