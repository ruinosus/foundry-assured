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

from app.core.settings import settings
from app.core.tenant import tenant_config


def selfwiki_configured() -> bool:
    if settings.deployment_mode == "shared":
        return True  # shared: mount globally; per-tenant decided at request time
    cfg = tenant_config()
    return bool(cfg.azure_search_endpoint and cfg.selfwiki_search_knowledge_base)
