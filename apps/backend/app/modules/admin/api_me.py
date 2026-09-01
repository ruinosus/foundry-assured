"""GET /me — the signed-in caller's identity + app roles.

The `roles` claim lives in the ACCESS token (audience = this API app), not the SPA's id
token, so the frontend can't read the API-app roles locally — it asks here. Used to show/hide
the admin UI (the real gate is still server-side on each admin endpoint). Any signed-in user
may call it; in local dev (auth off) it returns all roles so the UI stays usable.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.shared.auth import APP_ROLES, require_user
from app.shared.settings import settings

router = APIRouter()


@router.get("/me", dependencies=[Depends(require_user)])
def me():
    from app.shared.auth import current_user

    if not settings.auth_enabled:
        return {
            "name": "dev",
            "oid": "dev-local",
            "tenant_id": None,
            "roles": list(APP_ROLES),
            "areas": [],
            "auth": False,
        }
    user = current_user()
    from app.modules.tenancy.public import (
        authorized_areas,
        current_tenant_id,
        tenant_store,
    )

    store = tenant_store()
    tenant = store.get(current_tenant_id()) if store is not None else None
    areas = authorized_areas(user, tenant) if tenant is not None else ()
    return {
        "name": getattr(user, "name", None),
        "oid": getattr(user, "oid", None),
        "tenant_id": getattr(user, "tid", None),
        "roles": list(getattr(user, "roles", []) or []),
        "areas": [
            {
                "id": area.id,
                "name": area.name,
                "status": area.status,
                "revision": area.revision,
                "permissions": list(area.permissions),
            }
            for area in areas
        ],
        "auth": True,
    }
