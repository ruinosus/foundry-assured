"""Tenant-area authorization derived from validated Entra identity claims."""

from __future__ import annotations

import contextvars
from dataclasses import dataclass
from typing import TYPE_CHECKING, Annotated
from uuid import UUID

from fastapi import Depends, Header, HTTPException, status

from app.shared import auth
from app.shared.auth import APP_ROLES

if TYPE_CHECKING:
    from app.modules.tenancy.internal.tenant_store import TenantRecord


@dataclass(frozen=True)
class AreaAccess:
    id: str
    name: str
    status: str
    revision: int
    permissions: tuple[str, ...]


_current_area: contextvars.ContextVar[AreaAccess | None] = contextvars.ContextVar(
    "current_authoring_area", default=None
)


def authorized_areas(user, tenant: TenantRecord) -> tuple[AreaAccess, ...]:
    if user is None or getattr(user, "tid", None) != tenant.tid:
        return ()

    roles = tuple(role for role in APP_ROLES if role in set(getattr(user, "roles", None) or ()))
    if not roles:
        return ()

    groups = set(getattr(user, "groups", None) or ())
    return tuple(
        AreaAccess(
            id=area.id,
            name=area.name,
            status=area.status,
            revision=area.revision,
            permissions=roles,
        )
        for area in tenant.areas
        if area.status == "active" and groups.intersection(area.entra_group_ids)
    )


def resolve_area(user, tenant: TenantRecord, area_id: str) -> AreaAccess | None:
    area = next((area for area in authorized_areas(user, tenant) if area.id == area_id), None)
    _current_area.set(area)
    return area


def current_area() -> AreaAccess | None:
    return _current_area.get()


async def require_area(
    area_id: Annotated[UUID, Header(alias="X-Area-ID")],
    _user=Depends(auth.require_user),
) -> AreaAccess:
    from app.modules.tenancy.internal.tenant import current_tenant_id
    from app.modules.tenancy.internal.tenant_resolution import tenant_store

    store = tenant_store()
    if store is None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "AREA_STORE_UNAVAILABLE")
    tenant = store.get(current_tenant_id())
    area = resolve_area(auth.current_user(), tenant, str(area_id)) if tenant is not None else None
    if area is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AREA_NOT_FOUND")
    return area
