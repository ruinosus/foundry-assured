"""The helpdesk workflow: triage → retrieve → resolve → escalate.

`build_helpdesk_workflow` is the whole surface. The HITL gate is structural and stays inside
`internal/escalation.py`: the ticket is created only in the response handler, after explicit
human approval AND an Approver/Admin role check (RULE #5). That role check is deliberately
code, not declaration — ADR-018.
"""

from app.modules.helpdesk.internal.escalation import EscalationExecutor
from app.modules.helpdesk.internal.graph import build_helpdesk_workflow
from app.modules.helpdesk.internal.memory import build_memory_provider
from app.modules.helpdesk.internal.stream_fix import OrderedAgentFrameworkWorkflow

__all__ = [
    "EscalationExecutor",
    "OrderedAgentFrameworkWorkflow",
    "build_helpdesk_workflow",
    "build_memory_provider",
]
