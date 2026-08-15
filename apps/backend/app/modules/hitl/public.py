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

from dataclasses import dataclass, field
from typing import Literal

from app.shared.auth import current_roles, has_role

DecisionType = Literal["approve", "edit", "reject", "respond"]

__all__ = [
    "ApprovalDecision",
    "ApprovalRequest",
    "DecisionType",
    "NotAuthorized",
    "decide",
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

    if decision_type == "edit":
        if not args:
            raise NotAuthorized(
                f"'edit' on '{request.action}' carries no arguments — an edit that changes "
                "nothing is an approval, and must be sent as one"
            )
        return ApprovalDecision("edit", args=dict(args), approver_roles=tuple(sorted(current_roles())))

    return ApprovalDecision(
        decision_type, message=message, approver_roles=tuple(sorted(current_roles()))
    )
