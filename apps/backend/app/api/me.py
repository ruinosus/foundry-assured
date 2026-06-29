"""GET /me — the signed-in caller's identity + app roles.

The `roles` claim lives in the ACCESS token (audience = this API app), not the SPA's id
token, so the frontend can't read the API-app roles locally — it asks here. Used to show/hide
the admin UI (the real gate is still server-side on each admin endpoint). Any signed-in user
may call it; in local dev (auth off) it returns all roles so the UI stays usable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.core.auth import APP_ROLES, require_user
from app.core.settings import settings

router = APIRouter()


@router.get("/me", dependencies=[Depends(require_user)])
def me():
    from app.core.auth import current_user

    if not settings.auth_enabled:
        return {"name": "dev", "oid": "dev-local", "roles": list(APP_ROLES), "auth": False}
    user = current_user()
    return {
        "name": getattr(user, "name", None),
        "oid": getattr(user, "oid", None),
        "roles": list(getattr(user, "roles", []) or []),
        "auth": True,
    }
