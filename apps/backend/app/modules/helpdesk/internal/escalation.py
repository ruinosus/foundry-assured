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

from app.modules.hitl.public import ApprovalRequest, NotAuthorized, decide
from app.modules.tickets.public import create_ticket

TICKET_PREFIX = "TICKET:"

#: A linha OPCIONAL com o porquê. `resolve` a emite logo abaixo do TICKET.
#:
#: Opcional não é descuido: prompt e código publicam SEPARADO (ADR-014 — o prompt vai por
#: `push-prompts.sh` e aplica no restart; o código vai por deploy). Um backend novo pode rodar
#: com um prompt antigo por horas, e nesse intervalo a escalação precisa continuar funcionando
#: sem o motivo em vez de quebrar.
WHY_PREFIX = "WHY:"


@dataclass
class TicketApprovalRequest:
    """Shown to the developer: approve opening a ticket with this summary.

    `reason` é o PORQUÊ — o que levou o agente a concluir que precisa escalar. Ele existe porque
    aprovar sabendo só o QUE será escrito é decidir com metade da informação: "substituir a
    estação do desenvolvedor" pode ser óbvio ou absurdo dependendo do que veio antes.

    É TEXTO DO MODELO, não fato verificado, e a interface precisa dizer isso. Um porquê exibido
    com a mesma tipografia do resumo vira uma segunda afirmação com ar de dado — e o aprovador
    passa a aprovar PELA justificativa em vez de pelo conteúdo, que é o oposto do que o gate
    existe para fazer.
    """

    summary: str
    reason: str = ""


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
            # Primeira linha é o resumo; uma linha WHY: abaixo dela, quando houver, é o porquê.
            # Duas linhas em vez de um separador no meio da frase: um resumo pode conter
            # qualquer pontuação, e parsear por delimitador embutido quebraria no primeiro
            # chamado que citasse o próprio delimitador.
            linhas = [linha.strip() for linha in text.splitlines() if linha.strip()]
            summary = linhas[0][len(TICKET_PREFIX) :].strip() or "Escalation requested"
            reason = next(
                (
                    linha[len(WHY_PREFIX) :].strip()
                    for linha in linhas[1:]
                    if linha.upper().startswith(WHY_PREFIX)
                ),
                "",
            )
            # Pause for approval — the response arrives in on_decision below.
            await ctx.request_info(
                request_data=TicketApprovalRequest(summary=summary, reason=reason),
                # `object`, not `bool`: the approver may now EDIT the summary, so the answer
                # can be a decision dict as well as the legacy boolean. Both are handled in
                # `on_decision` (ADR-019).
                response_type=object,
            )
        else:
            # No ticket needed — pass the resolve answer through as the output.
            await ctx.yield_output(text)

    @response_handler
    async def on_decision(
        self,
        request: TicketApprovalRequest,
        answer: object,
        ctx: WorkflowContext[str, str],
    ) -> None:
        """Apply the approver's decision — approve, edit, or reject.

        `edit` is why this is no longer a boolean (ADR-019): opening a ticket whose summary is
        wrong, because refusing was the only alternative, is not oversight. The approver can
        now correct it.

        Two shapes are accepted, and the legacy one is not deprecated by accident:

            True / False                      the original boolean (what today's UI sends)
            {"type": "...", "args": {...}}    a decision, where `edit` carries the correction
                                              and `reject` carries `message` — the reason

        Authorization is NOT decided here — `hitl.decide()` owns it, and it refuses `edit`
        from a caller without the Approver role just as it refuses `approve`. Editing runs the
        action, so it needs the same authority; treating it as "just a tweak" is exactly how
        the RULE #5 gate would quietly grow a hole.
        """
        decision_type, args, message = _read_answer(answer)

        approval = ApprovalRequest(
            action="create_ticket",
            args={"summary": request.summary},
            required_role=("Approver", "Admin"),
            allowed_decisions=("approve", "edit", "reject"),
        )

        try:
            decision = decide(approval, decision_type, args=args, message=message)
        except NotAuthorized as refusal:
            # The refusal text is deliberately about the ROLE, not the person: the approver's
            # identity belongs in the audit log, not in a chat message (I-10).
            await ctx.yield_output(
                f"Decisão recusada: {refusal}. Nenhum chamado foi aberto — peça a um aprovador."
            )
            return

        if decision.type == "reject":
            # O MOTIVO VOLTA PARA A CONVERSA. Uma recusa sem motivo obriga quem pediu a adivinhar
            # o que corrigir — e obriga o modelo a tentar de novo igual. O texto é do aprovador,
            # dito por ele; a TRILHA guarda só que houve motivo e o tamanho (ver `hitl.public`),
            # porque conteúdo não entra na trilha.
            motivo = f' Motivo: "{decision.message}"' if decision.message else ""
            await ctx.yield_output(
                f"No ticket opened.{motivo} Tell me if you'd like to try something else."
            )
            return

        # `edit` supplies a corrected summary; `approve` keeps the one the model proposed.
        summary = decision.args.get("summary", request.summary) if decision.type == "edit" else request.summary

        ticket = create_ticket(summary, domain="helpdesk")
        edited_note = " (editado pelo aprovador)" if decision.type == "edit" else ""
        await ctx.yield_output(
            f'✅ Ticket {ticket["id"]} opened — "{ticket["summary"]}"{edited_note}. '
            "The team will follow up."
        )


#: Teto do motivo da recusa. Ele atravessa para a conversa e o tamanho vai para a trilha; sem
#: teto, um payload de megabytes entraria no output do workflow. Truncar é melhor que recusar a
#: recusa — parar uma ação nunca pode falhar por causa do formulário.
MAX_MOTIVO = 500


def _read_answer(answer: object) -> tuple[str, dict, str]:
    """Normalize the accepted answer shapes into (decision_type, args, message).

    Anything unrecognized becomes a REJECT rather than an approval — a malformed payload must
    never be the reason a ticket gets opened (fail-closed, RULE #5).

    `message` só é lido para `reject`: um motivo anexado a um `approve` seria um campo que
    ninguém lê depois, e num `edit` a correção JÁ é a mensagem.
    """
    if isinstance(answer, bool):
        return ("approve" if answer else "reject", {}, "")
    if isinstance(answer, dict):
        decision_type = str(answer.get("type", "")).lower()
        if decision_type in ("approve", "edit", "reject"):
            args = answer.get("args") or {}
            bruto = answer.get("message")
            message = str(bruto)[:MAX_MOTIVO].strip() if decision_type == "reject" and bruto else ""
            return decision_type, dict(args) if isinstance(args, dict) else {}, message
    return "reject", {}, ""
