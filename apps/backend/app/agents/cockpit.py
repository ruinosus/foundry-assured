"""Cockpit expert agent — a second domain alongside the helpdesk.

Same Foundry IQ pattern as the concierge, pointed at the **cockpit-kb** (the Cockpit
platform docs ingested by app/knowledge/ingest_cockpit.py). Pure grounded Q&A — no
workflow steps or ticket escalation; the Cockpit corpus is reference knowledge.

The Cockpit KB is org-wide (not per-user), so this runs under the app's own identity
(DefaultAzureCredential), not OBO. The /cockpit endpoint still requires sign-in.
"""

from pathlib import Path

from agent_framework import Agent, FileSkillsSource, SkillsProvider
from agent_framework.azure import AzureAISearchContextProvider
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from app.agents.prompts import COCKPIT_INSTRUCTIONS
from app.core.settings import settings

# Agent Skills (open SKILL.md standard) — the grounded-qa skill adapted from
# microsoft/skills deep-wiki carries the retrieval/answering discipline (cite, decline
# off-corpus, prefer authoritative architecture docs) so it isn't hand-rolled in the prompt.
_SKILLS_DIR = Path(__file__).parent / "skills"


def cockpit_configured() -> bool:
    return bool(settings.azure_search_endpoint and settings.cockpit_search_knowledge_base)


def build_cockpit_agent() -> Agent:
    """A grounded expert over the Cockpit knowledge base, using the grounded-qa skill."""
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=settings.foundry_project_endpoint or None,
        model=settings.foundry_model,
        credential=credential,
    )
    # Semantic mode (not agentic): agentic retrieval makes the model emit a per-turn
    # search *tool call*, and over AG-UI the prior turn's tool call replays without its
    # paired output on the next message → the Responses API rejects it ("No tool output
    # found for function call") and the 2nd turn fails. Semantic mode injects retrieved
    # context with no tool call, so multi-turn just works; it still grounds well.
    search = AzureAISearchContextProvider(
        endpoint=settings.azure_search_endpoint,
        index_name=settings.cockpit_search_index,
        credential=credential,
        mode="semantic",
    )
    skills = SkillsProvider(FileSkillsSource([str(_SKILLS_DIR)]))
    return client.as_agent(
        name="CockpitExpert",
        description="Avanade Cockpit platform expert grounded in the Cockpit knowledge base.",
        instructions=COCKPIT_INSTRUCTIONS,
        context_providers=[search, skills],
    )
