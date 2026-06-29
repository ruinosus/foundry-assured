"""Admin API — user lifecycle + app-role assignment, all Admin-gated.

Every endpoint requires the `Admin` app role (server-side, via require_role) and drives
Microsoft Graph app-only (app/services/graph.py). The frontend /admin/users page calls these;
no Graph from the browser. See docs/RBAC-AND-USER-MANAGEMENT-PLAN.md.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import APP_ROLES, require_role
from app.services import graph
from app.services.graph import GraphError

router = APIRouter(prefix="/admin", tags=["admin"])

# One dependency instance reused across the routes — the Admin gate.
_admin = Depends(require_role("Admin"))


def _guard(fn):
    """Run a Graph call, translating GraphError → HTTP so the UI sees a clean message."""
    try:
        return fn()
    except GraphError as e:
        raise HTTPException(status_code=e.status, detail=e.message) from e


class InviteBody(BaseModel):
    email: str
    redirect_url: str | None = None


class CreateUserBody(BaseModel):
    display_name: str
    user_principal_name: str
    password: str


class AssignBody(BaseModel):
    principal_id: str
    role: str


@router.get("/roles", dependencies=[_admin])
def roles() -> dict[str, list[str]]:
    """The app's role vocabulary (for the UI's assign dropdown)."""
    return {"roles": list(APP_ROLES)}


@router.get("/users", dependencies=[_admin])
def users(top: int = 50) -> dict[str, list[dict]]:
    return {"users": _guard(lambda: graph.list_users(top))}


@router.post("/users/invite", dependencies=[_admin])
def invite(body: InviteBody) -> dict:
    redirect = body.redirect_url or "https://ruinosus.github.io/foundry-assured/"
    return _guard(lambda: graph.invite_user(body.email, redirect))


@router.post("/users", dependencies=[_admin])
def create(body: CreateUserBody) -> dict:
    return _guard(lambda: graph.create_user(body.display_name, body.user_principal_name, body.password))


@router.delete("/users/{user_id}", dependencies=[_admin])
def remove(user_id: str) -> dict:
    _guard(lambda: graph.delete_user(user_id))
    return {"deleted": user_id}


@router.get("/role-assignments", dependencies=[_admin])
def role_assignments() -> dict[str, list[dict]]:
    return {"assignments": _guard(graph.list_role_assignments)}


@router.post("/role-assignments", dependencies=[_admin])
def assign(body: AssignBody) -> dict:
    return _guard(lambda: graph.assign_role(body.principal_id, body.role))


@router.delete("/role-assignments/{assignment_id}", dependencies=[_admin])
def revoke(assignment_id: str) -> dict:
    _guard(lambda: graph.revoke_role(assignment_id))
    return {"revoked": assignment_id}
