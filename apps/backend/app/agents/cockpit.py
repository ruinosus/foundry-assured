"""Cockpit expert agent — a second domain alongside the helpdesk.

Same Foundry IQ pattern as the concierge, pointed at the **cockpit-kb** (the Cockpit
platform docs ingested by app/knowledge/ingest_docbundles.py). Pure grounded Q&A — no
workflow steps or ticket escalation; the Cockpit corpus is reference knowledge.

Grounding is Microsoft's documented Foundry IQ pattern: the AzureAISearchContextProvider
(agentic retrieval) injects the relevant Cockpit docs — with citations — into context,
and the answering discipline lives in COCKPIT_INSTRUCTIONS. No consume-side Agent Skill:
the KB *is* the knowledge, so a retrieval-discipline skill (and its read_skill_resource
tool) only added noise. Wiki *generation* still uses the deep-wiki skills.

The Cockpit KB is org-wide (not per-user), so this runs under the app's own identity
(DefaultAzureCredential), not OBO. The /cockpit endpoint still requires sign-in.
"""

from app.core.settings import settings
from app.core.tenant import tenant_config


def cockpit_configured() -> bool:
    if settings.deployment_mode == "shared":
        return True  # shared: mount globally; per-tenant decided at request time
    cfg = tenant_config()
    return bool(cfg.azure_search_endpoint and cfg.cockpit_search_knowledge_base)
