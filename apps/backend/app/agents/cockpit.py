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
from agent_framework.foundry import FoundryChatClient
from azure.identity import DefaultAzureCredential

from app.agents.prompts import COCKPIT_INSTRUCTIONS
from app.agents.secure_search import SecureAzureAISearchProvider
from app.core.settings import settings
from app.core.tenant import tenant_config


def cockpit_configured() -> bool:
    if settings.deployment_mode == "shared":
        return True  # shared: mount globally; per-tenant decided at request time
    cfg = tenant_config()
    return bool(cfg.azure_search_endpoint and cfg.cockpit_search_knowledge_base)


def build_cockpit_agent() -> Agent:
    """A grounded expert over the Cockpit knowledge base (Foundry IQ agentic retrieval)."""
    cfg = tenant_config()
    credential = DefaultAzureCredential()
    client = FoundryChatClient(
        project_endpoint=cfg.foundry_project_endpoint or None,
        model=cfg.foundry_model,
        credential=credential,
    )
    # Agentic retrieval (Foundry IQ KB query planning) — best quality on broad questions.
    # Runs in a context-provider hook (before_run), injecting the retrieved Cockpit docs
    # (with citations) into context; it does NOT emit a model tool call, so multi-turn
    # over AG-UI is clean without any tool-message sanitizing.
    #
    # reasoning_effort="medium" enables iterative query planning (vs "minimal" = a single
    # semantic search). Measured on the MCP-enumeration golden it lifts retrieval recall
    # 6/12 → 8/12 (8/9 servers) — the completeness lever (Phase 2 of the assurance plan).
    # Trade-off: ~2x context + higher latency; worth it for a completeness-first KB agent.
    # SecureAzureAISearchProvider (Phase 4): passes the signed-in user's identity as
    # x-ms-query-source-authorization so the KB trims results to what they're entitled
    # to. With auth off (local dev) it behaves exactly like the base provider.
    search = SecureAzureAISearchProvider(
        endpoint=cfg.azure_search_endpoint,
        knowledge_base_name=cfg.cockpit_search_knowledge_base,
        credential=credential,
        mode="agentic",
        retrieval_reasoning_effort="medium",
    )
    return client.as_agent(
        name="CockpitExpert",
        description="Avanade Cockpit platform expert grounded in the Cockpit knowledge base.",
        instructions=COCKPIT_INSTRUCTIONS,
        context_providers=[search],
    )
