"""The grounded archetype: cited Q&A over a knowledge base (techdocs, selfwiki).

Every answer this module produces must carry at least one source citation — RULE #4, enforced
by the eval policy gate, not by a protocol.

`PerRequestAgent` lives here because the grounded domains needed it first; `platform_ops`
reuses it. ADR-018 decided NOT to lift it into an orchestration abstraction: it is 24 lines of
real code, and a port layer for a second runtime that does not exist is premature.
"""

from app.modules.grounded.internal.concierge import (
    _knowledge_configured as knowledge_configured,
)
from app.modules.grounded.internal.concierge import (
    build_concierge_agent,
)
from app.modules.grounded.internal.framework_agent import (
    build_grounded_agent,
    build_grounded_workflow,
    mount_grounded_via_framework,
    via_framework,
)
from app.modules.grounded.internal.grounded import (
    SYNTHESIS_DIRECTIVE,
    build_synthesis_kwargs,
    stream_grounded,
)
from app.modules.grounded.internal.per_request import PerRequestAgent
from app.modules.grounded.internal.retrieval_provider import GroundedRetrieval
from app.modules.grounded.internal.selfwiki import selfwiki_configured
from app.modules.grounded.internal.sources_executor import SourcesExecutor
from app.modules.grounded.internal.techdocs import techdocs_configured

__all__ = [
    "SYNTHESIS_DIRECTIVE",
    "GroundedRetrieval",
    "PerRequestAgent",
    "SourcesExecutor",
    "build_concierge_agent",
    "build_grounded_agent",
    "build_grounded_workflow",
    "build_synthesis_kwargs",
    "knowledge_configured",
    "mount_grounded_via_framework",
    "selfwiki_configured",
    "stream_grounded",
    "techdocs_configured",
    "via_framework",
]
