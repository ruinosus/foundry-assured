"""On-call triage — the LangGraph domain (ADR-020).

Sits beside four Agent Framework domains on purpose. The assurance layer is the product here,
and a guarantee demonstrated on one runtime has not been demonstrated: this domain is how the
same contracts get proved somewhere else.

It is also the only place `edit` exists natively — the approver correcting an action before it
runs, which the Agent Framework's boolean approval cannot express (ADR-019).

⚠ `oncall_configured()` gates the mount. The graph needs an Azure OpenAI endpoint AND a
checkpointer; the current checkpointer is `InMemorySaver`, which is correct for one process
and WRONG for `shared` deployment mode — an interrupt must survive a request landing on another
replica. Do not enable this domain in shared mode until the checkpointer is durable.
"""

from app.modules.oncall.internal.graph import (
    INTERRUPT_ON,
    ONCALL_INSTRUCTIONS,
    build_oncall_graph,
)
from app.shared.settings import settings

__all__ = ["INTERRUPT_ON", "ONCALL_INSTRUCTIONS", "build_oncall_graph", "oncall_configured"]


def oncall_configured() -> bool:
    """True when the LangGraph domain can actually serve.

    Fail-closed on shared mode: see the checkpointer warning in the module docstring. A domain
    that mounts but loses interrupts under load is worse than a domain that does not mount.
    """
    import os

    if settings.deployment_mode == "shared":
        return False
    return bool(os.environ.get("AZURE_OPENAI_ENDPOINT") and settings.oncall_model)
