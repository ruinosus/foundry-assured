"""Escalation step — human-in-the-loop ticket approval (Phase 4).

This is the final node of the workflow. If the resolve agent flagged that a
ticket is needed (its answer is exactly "TICKET: <summary>"), this executor
pauses the workflow with ctx.request_info() and waits for the developer's
decision. The ticket is created ONLY in the response handler, after approval —
so "no ticket without approval" holds structurally.

Why a workflow request_info node instead of an approval-mode tool on the agent:
the AG-UI workflow adapter (agent-framework-ag-ui 1.0.0rc5) duplicates the
TOOL_CALL_START for an agent's approval-gated tool call, breaking the stream. The
native workflow request/response mechanism emits a clean request_info interrupt
that CopilotKit renders via useInterrupt. (This also matches the spec's original
triage -> retrieve -> resolve -> escalate design.)

APIs verified against agent-framework 1.9.0.
"""

# NOTE: no `from __future__ import annotations` — the @response_handler validator
# inspects the real WorkflowContext annotation, which string annotations break.
from dataclasses import dataclass

from agent_framework import (
    AgentExecutorResponse,
    Executor,
    WorkflowContext,
    handler,
    response_handler,
)

from app.core.auth import has_role
from app.tools.tickets import create_ticket

TICKET_PREFIX = "TICKET:"


@dataclass
class TicketApprovalRequest:
    """Shown to the developer: approve opening a ticket with this summary."""

    summary: str


class EscalationExecutor(Executor):
    """Final workflow step: gate ticket creation behind human approval."""

    def __init__(self) -> None:
        super().__init__(id="escalate")

    @handler
    async def on_resolve(
        self, response: AgentExecutorResponse, ctx: WorkflowContext[str, str]
    ) -> None:
        text = (response.agent_response.text or "").strip()
        if text.upper().startswith(TICKET_PREFIX):
            summary = text[len(TICKET_PREFIX) :].strip() or "Escalation requested"
            # Pause for approval — the response arrives in on_decision below.
            await ctx.request_info(
                request_data=TicketApprovalRequest(summary=summary),
                response_type=bool,
            )
        else:
            # No ticket needed — pass the resolve answer through as the output.
            await ctx.yield_output(text)

    @response_handler
    async def on_decision(
        self,
        request: TicketApprovalRequest,
        approved: bool,
        ctx: WorkflowContext[str, str],
    ) -> None:
        if approved and not has_role("Approver", "Admin"):
            # RBAC gate: approving the escalation is an Approver/Admin action. The human
            # approval above is necessary but not sufficient — the approver must hold the
            # role. (No-op when auth is off — local dev approves freely.)
            await ctx.yield_output(
                "Aprovação recebida, mas você não tem o papel **Approver** para abrir "
                "chamados. Nenhum ticket foi aberto — peça a um aprovador."
            )
            return
        if approved:
            # Real, persisted action (viewable at GET /tickets and the /tickets page),
            # gated by the human approval above + the Approver role.
            ticket = create_ticket(request.summary)
            await ctx.yield_output(
                f'✅ Ticket {ticket["id"]} opened — "{ticket["summary"]}". '
                "The team will follow up."
            )
        else:
            await ctx.yield_output(
                "No ticket opened. Tell me if you'd like to try something else."
            )
