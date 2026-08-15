"""The role gate holds for every decision that runs the action — `edit` included.

`edit` is the decision this module exists for, and it is also the one most likely to become a
hole: it is easy to read as "a small change to an approval" and forget that it CAUSES THE
ACTION TO RUN. An approver-less edit would open the ticket while the audit trail says a human
corrected it.

RULE #5 says `create_ticket` fires only after explicit human approval by an Approver or Admin.
These are the ways that could quietly stop being true.

    uv run python -m tests.hitl.decision_test
"""

from __future__ import annotations

import sys

from app.modules.hitl.public import ApprovalRequest, NotAuthorized, decide
from app.shared import auth
from app.shared.settings import settings


class _User:
    def __init__(self, roles):
        self.roles = roles
        self.oid = "u-1"


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    def refuses(fn) -> bool:
        try:
            fn()
        except NotAuthorized:
            return True
        return False

    request = ApprovalRequest(action="create_ticket", args={"summary": "pod crashloop"})
    original_auth = settings.auth_enabled if hasattr(settings, "auth_enabled") else None

    # auth_enabled is a derived property; drive the roles through the contextvar instead.
    settings.entra_tenant_id = settings.entra_tenant_id or "t"
    settings.entra_api_client_id = settings.entra_api_client_id or "c"
    try:
        # --- A caller WITHOUT the role cannot run the action, by any route ------------------
        auth._current_user.set(_User(["Reader"]))
        check("Reader cannot approve", refuses(lambda: decide(request, "approve")))
        check(
            "Reader cannot EDIT — editing runs the action too",
            refuses(lambda: decide(request, "edit", args={"summary": "corrected"})),
        )
        check("Reader CAN reject (stopping is always allowed)", decide(request, "reject").type == "reject")

        # --- An Approver can do both, and the edit carries the corrected args ---------------
        auth._current_user.set(_User(["Approver"]))
        approved = decide(request, "approve")
        check("Approver can approve", approved.type == "approve")
        check("approve carries NO args (cannot be mistaken for a confirmed edit)", approved.args == {})

        edited = decide(request, "edit", args={"summary": "Kubernetes pod in CrashLoopBackOff"})
        check("Approver can edit", edited.type == "edit")
        check(
            "the edit carries the CORRECTED arguments",
            edited.args["summary"] == "Kubernetes pod in CrashLoopBackOff",
        )
        check("the decision records the approver's ROLE, not their identity",
              edited.approver_roles == ("Approver",) and "u-1" not in str(edited))

        # --- An empty edit is not an approval in disguise -----------------------------------
        check("an edit with no arguments is refused", refuses(lambda: decide(request, "edit", args={})))

        # --- A decision the request does not allow is refused --------------------------------
        check(
            "a decision type outside allowed_decisions is refused",
            refuses(lambda: decide(request, "respond", message="handled offline")),
        )
        limited = ApprovalRequest(
            action="create_ticket", args={}, allowed_decisions=("approve", "edit", "reject", "respond")
        )
        check("…and allowed when the request permits it",
              decide(limited, "respond", message="handled offline").type == "respond")
    finally:
        auth._current_user.set(None)
        if original_auth is not None:
            pass

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ every decision that runs the action requires the role; edit is not a loophole.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
