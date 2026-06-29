"""Selfwiki agent — the mechanism turned on itself (the "deep-wiki daqui").

A third domain alongside the helpdesk and the Cockpit expert: same Foundry IQ pattern,
but the knowledge base (**selfwiki-kb**) is a deep-wiki generated from THIS monorepo's
own source — apps/backend, apps/frontend, infra and docs (see
app/knowledge/wiki_builder.py + the selfwiki ingest). It's the dogfood: we point the
assurance mechanism at our own repo and ask it to answer questions about the project,
grounded only in what the wiki captured from the real code.

Pure grounded Q&A — no workflow steps or ticket escalation. Unlike Cockpit, this corpus
is single-audience (the repo is public), so there's no per-user ACL trim: it runs under
the app's own identity (DefaultAzureCredential) with the plain agentic-retrieval provider.
The /selfwiki endpoint still requires sign-in. APIs mirror app/agents/cockpit.py
(agent-framework 1.9.0).
"""

from agent_framework import Agent
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from app.agents.grounded_search import GroundedAzureAISearchProvider
from app.agents.prompts import SELFWIKI_INSTRUCTIONS
from app.core.tenant import tenant_config


def selfwiki_configured() -> bool:
    return bool(tenant_config().azure_search_endpoint and tenant_config().selfwiki_search_knowledge_base)


def build_selfwiki_agent() -> Agent:
    """A grounded expert over this project's own deep-wiki (Foundry IQ agentic retrieval)."""
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=tenant_config().foundry_project_endpoint or None,
        model=tenant_config().foundry_model,
        credential=credential,
    )
    # Agentic retrieval (reasoning_effort="medium" = iterative query planning) — the
    # completeness lever for broad "how does X work across the project" questions, exactly
    # as in the Cockpit agent. No ACL trim here: the selfwiki corpus is single-audience,
    # so the base provider (not SecureAzureAISearchProvider) is the honest fit.
    # Agentic retrieval (completeness) with a direct-semantic FALLBACK: the Foundry IQ
    # agentic path sometimes returns an empty context even when the index has the answer
    # (e.g. operational "what's the cost" queries), which made the agent decline blind.
    # GroundedAzureAISearchProvider falls back to a direct search on the index so the
    # agent grounds whenever the content exists.
    search = GroundedAzureAISearchProvider(
        endpoint=tenant_config().azure_search_endpoint,
        knowledge_base_name=tenant_config().selfwiki_search_knowledge_base,
        credential=credential,
        mode="agentic",
        retrieval_reasoning_effort="medium",
        fallback_index=tenant_config().selfwiki_search_index,
    )
    return client.as_agent(
        name="SelfWikiExpert",
        description="Expert on the foundry-assured project, grounded in its own generated deep-wiki.",
        instructions=SELFWIKI_INSTRUCTIONS,
        context_providers=[search],
    )
