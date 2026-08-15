"""TechDocs expert agent — a second domain alongside the helpdesk.

Same Foundry IQ pattern as the concierge, pointed at the **techdocs-kb** (the TechDocs
platform docs ingested by app/knowledge/ingest_docbundles.py). Pure grounded Q&A — no
workflow steps or ticket escalation; the TechDocs corpus is reference knowledge.

Grounding is Microsoft's documented Foundry IQ pattern: the AzureAISearchContextProvider
(agentic retrieval) injects the relevant TechDocs docs — with citations — into context,
and the answering discipline lives in TECHDOCS_INSTRUCTIONS. No consume-side Agent Skill:
the KB *is* the knowledge, so a retrieval-discipline skill (and its read_skill_resource
tool) only added noise. Wiki *generation* still uses the deep-wiki skills.

The TechDocs KB is org-wide (not per-user), so this runs under the app's own identity
(DefaultAzureCredential), not OBO. The /techdocs endpoint still requires sign-in.
"""

from app.shared.settings import settings
from app.modules.tenancy.public import tenant_config


def techdocs_configured() -> bool:
    if settings.deployment_mode == "shared":
        return True  # shared: mount globally; per-tenant decided at request time
    cfg = tenant_config()
    return bool(cfg.azure_search_endpoint and cfg.techdocs_search_knowledge_base)
