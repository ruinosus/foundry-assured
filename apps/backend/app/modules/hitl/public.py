"""Human-in-the-loop decisions: approve · edit · reject · respond, with the role gate.

The Agent Framework's approval is a boolean — accept or refuse the action exactly as the model
proposed it. ADR-019 adopted LangChain's richer decision set because `edit` is a product
requirement: the approver must be able to CORRECT an action before it runs. Opening a ticket
whose summary is wrong, because the only alternative was refusing it, is not oversight.

What this module owns is the part NEITHER framework has: **who may decide**. `required_role`
has no equivalent in LangChain or in the Agent Framework, and RULE #5 depends on it — a ticket
is created only after explicit human approval AND only by an Approver or Admin.

The decision shapes mirror LangChain's `DecisionType` deliberately (verified against the
installed package, `langchain/agents/middleware/human_in_the_loop.py`):

    approve   run the action as proposed
    edit      run it with the approver's corrected arguments
    reject    do not run it; the message goes back to the model as a ToolMessage
    respond   do not run it; the approver answers on the tool's behalf

Mirroring rather than inventing means a decision made here can be handed straight to
`HumanInTheLoopMiddleware` without translation, and that a future LangGraph domain and today's
Agent Framework domains speak the same vocabulary to the same ApprovalCard.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field, replace
from typing import TYPE_CHECKING, Literal

from app.shared.auth import current_roles, has_role

if TYPE_CHECKING:
    from app.modules.hitl.internal.langgraph_recording import RecordingHumanInTheLoop

logger = logging.getLogger(__name__)

DecisionType = Literal["approve", "edit", "reject", "respond"]

__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "DecisionType",
    "NotAuthorized",
    "decide",
    "recording_hitl",
]


class NotAuthorized(Exception):
    """The caller may not decide this request. Fail-closed: never falls through to approve."""


@dataclass(frozen=True)
class ApprovalRequest:
    """One action awaiting a human.

    `required_role` is the only field with no counterpart in either framework. It is not
    advisory: `decide()` refuses a decision from a caller who does not hold it.
    """

    action: str
    args: dict
    required_role: tuple[str, ...] = ("Approver", "Admin")
    allowed_decisions: tuple[DecisionType, ...] = ("approve", "edit", "reject")


@dataclass(frozen=True)
class ApprovalDecision:
    """What the human decided, and — for `edit` — with which arguments.

    `args` is populated ONLY for `edit`; for every other type it stays empty, so a caller
    cannot accidentally read stale proposed arguments as if a human had confirmed them.
    """

    type: DecisionType
    args: dict = field(default_factory=dict)
    message: str = ""
    approver_roles: tuple[str, ...] = ()
    #: O evento da TRILHA que registra esta decisão (ADR-023). Vazio significa que a decisão não
    #: foi registrada — e nesse caso a ação NÃO deve rodar: a RULE #5 diz que o chamado só abre
    #: após aprovação, e uma aprovação que não deixou rastro não é comprovável.
    audit: dict = field(default_factory=dict)


def decide(
    request: ApprovalRequest,
    decision_type: DecisionType,
    *,
    args: dict | None = None,
    message: str = "",
) -> ApprovalDecision:
    """Validate a human decision against the request, or raise.

    Three refusals, all fail-closed (RULE #5):

    1. a decision type the request does not allow;
    2. a caller without the required role — checked for EVERY type that would run the action,
       `edit` included. Editing is approving with different arguments, so it needs the same
       authority, and forgetting that would be the quiet way to bypass the gate;
    3. an `edit` with no arguments, which would silently run the model's original proposal
       while the audit trail claims a human corrected it.
    """
    if decision_type not in request.allowed_decisions:
        raise NotAuthorized(
            f"decision '{decision_type}' is not allowed for '{request.action}' "
            f"(allowed: {', '.join(request.allowed_decisions)})"
        )

    # `approve` and `edit` both cause the action to run — both need the role. `reject` and
    # `respond` only stop it, and stopping is always permitted.
    if decision_type in ("approve", "edit") and not has_role(*request.required_role):
        raise NotAuthorized(
            f"'{decision_type}' on '{request.action}' requires: "
            f"{' or '.join(request.required_role)}"
        )

    if decision_type == "edit" and not args:
        raise NotAuthorized(
            f"'edit' on '{request.action}' carries no arguments — an edit that changes "
            "nothing is an approval, and must be sent as one"
        )

    papeis = tuple(sorted(current_roles()))
    decisao = ApprovalDecision(
        decision_type,
        args=dict(args) if decision_type == "edit" else {},
        message=message if decision_type != "edit" else "",
        approver_roles=papeis,
    )
    return replace(decisao, audit=_registrar(request, decisao))


def _registrar(request: ApprovalRequest, decisao: ApprovalDecision) -> dict:
    """Grava a decisão na trilha. FAIL-CLOSED nas decisões que fazem a ação rodar.

    `approver_roles` já era calculado aqui e DESCARTADO — quem lia a decisão usava só `.type` e
    `.args`. O resultado é que a RULE #5 ("o chamado só abre após aprovação de um Approver") não
    tinha nenhum artefato que a comprovasse. Este é o evento que a comprova.

    Por que falhar fecha: se a gravação da aprovação falha e a ação roda mesmo assim, existe uma
    escrita sem rastro — exatamente o buraco que a trilha existe para não ter. `reject` e
    `respond` não fazem nada rodar, então uma falha de registro ali não pode impedir alguém de
    RECUSAR: bloquear a recusa transformaria uma falha de auditoria em pressão para aprovar.

    O que entra no evento: quem, o quê, quando, e — no `edit` — QUE CAMPOS foram corrigidos.
    Os VALORES não entram: eles são texto do usuário e do modelo, e a trilha é imutável.
    """
    from app.modules.audit.public import actor, actor_detail, record

    detalhe = {
        "decision": decisao.type,
        "roles": list(decisao.approver_roles),
        "required_role": list(request.required_role),
        # O oid ao lado do e-mail: o `actor` é legível, este é durável.
        **actor_detail(),
    }
    if decisao.type == "edit":
        # Só as CHAVES corrigidas. O valor corrigido é conteúdo, e conteúdo não entra na trilha.
        detalhe["edited_fields"] = sorted(decisao.args)

    try:
        return record(
            scope="approvals",
            actor=actor(),
            kind="approval",
            summary=f"{decisao.type} em {request.action}",
            ref=request.action,
            detail=detalhe,
        )
    except Exception as exc:
        if decisao.type in ("approve", "edit"):
            raise NotAuthorized(
                "A decisão não pôde ser registrada na trilha de auditoria, então a ação não vai "
                f"rodar: {exc}"
            ) from exc
        logger.warning("falha ao registrar a decisão '%s' na trilha: %s", decisao.type, exc)
        return {}


def recording_hitl(interrupt_on: dict, domain: str) -> RecordingHumanInTheLoop:
    """O middleware de HITL do LangGraph, com a decisão registrada na trilha (ADR-023).

    Importado por dentro DE PROPÓSITO, no mesmo espírito de `tenancy.internal.tenant.
    require_domain`: o contrato de decisão deste módulo (`decide`, `ApprovalDecision`) é limpo —
    não depende de nenhum framework de agente. Só quem usa grafo (`oncall`, `deepcall`) precisa
    do adaptador do LangGraph, e importar o LangChain no topo custaria essa dependência a quem só
    quer ler `decide`. Ver `tests/architecture/nucleo_limpo_test.py`.

    A anotação de retorno é só de type-check: `RecordingHumanInTheLoop` existe apenas sob
    `TYPE_CHECKING`, então `typing.get_type_hints()` levanta `NameError` para quem introspecta
    esta função em runtime (`pydantic.validate_call`, o FastAPI, `agent_framework.tool(...)`).
    """
    from app.modules.hitl.internal.langgraph_recording import (
        recording_hitl as _recording_hitl,
    )

    return _recording_hitl(interrupt_on, domain)
