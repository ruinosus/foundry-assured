"""create_ticket — a human-in-the-loop tool (Phase 4).

`approval_mode="always_require"` means the agent calling this tool does NOT
execute it directly: the workflow emits a function_approval_request that the
frontend renders as an approval card. Only when the developer approves does the
function body run. That enforces the rule "create_ticket only fires after human
approval" structurally — not by trusting the model.

Mock implementation: it doesn't hit a real ticketing system; it returns a
synthetic ticket id. Swap the body for a real Jira/ADO/MCP call later.

API verified: agent_framework.tool(approval_mode=...) -> FunctionTool.
"""

import uuid
from typing import Literal

from agent_framework import tool


@tool(
    approval_mode="always_require",
    description=(
        "Open an internal support ticket for the developer. Use this only when the "
        "issue needs action beyond the runbooks — e.g. escalation, or a request that "
        "can't be self-resolved. Requires the developer's approval before it is created."
    ),
)
def create_ticket(summary: str, priority: Literal["low", "medium", "high"] = "medium") -> str:
    """Open a support ticket.

    Args:
        summary: One-line description of the issue to escalate.
        priority: Ticket priority — low, medium, or high.
    """
    ticket_id = f"HD-{uuid.uuid4().hex[:6].upper()}"
    return f'Ticket {ticket_id} opened (priority: {priority}) — "{summary}"'
