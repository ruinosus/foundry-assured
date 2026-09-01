"""Per-tenant management API (shared mode) — config + connections, Admin-gated + tenant-scoped.

GET /tenant uses require_role("Admin") ALONE (it must tolerate a not-yet-onboarded tenant —
require_user would resolve the tenant and 403). The config/connection endpoints use require_user
(they require an onboarded tenant) + Admin. Every write is a read-modify-write of the caller's
own record (current_tenant_id()); no tid comes from the path. See the sub-project B design.
"""

from __future__ import annotations

import logging
from dataclasses import replace
from typing import Annotated, Literal
from uuid import UUID

from fastapi import (
    APIRouter,
    Depends,
    Header,
    HTTPException,
    Response,
    Security,
    status,
)
from fastapi_azure_auth.user import User
from pydantic import BaseModel, Field, model_validator

from app.modules.tenancy.internal import tenant_resolution as _tenant_resolution
from app.modules.tenancy.internal.onboarding import onboarding_guard
from app.modules.tenancy.internal.tenant import (
    DOMAIN_IDS,
    TenantConfig,
    current_tenant_id,
    domains_for_tier,
)
from app.modules.tenancy.internal.tenant_store import (
    AuthoringArea,
    Connection,
    TenantRecord,
    replace_area,
    validate_kind,
    with_area,
    with_connection,
    without_connection,
)
from app.shared.auth import _current_user, azure_scheme, require_role, require_user
from app.shared.settings import settings

router = APIRouter(prefix="/tenant", tags=["tenant"])
logger = logging.getLogger(__name__)
_admin = Depends(require_role("Admin"))
_user_admin = [Depends(require_user), Depends(require_role("Admin"))]


def _store():
    if _tenant_resolution.tenant_store() is None:
        raise HTTPException(503, "tenant store unavailable")
    return _tenant_resolution.tenant_store()


def _my_record() -> TenantRecord:
    rec = _store().get(current_tenant_id())
    if rec is None:
        raise HTTPException(404, "tenant not onboarded")
    return rec


class ConfigBody(BaseModel):
    foundry_project_endpoint: str = ""
    foundry_model: str = "gpt-5-mini"
    azure_search_endpoint: str = ""
    azure_search_knowledge_base: str = "helpdesk-kb"


class ConnectionBody(BaseModel):
    id: str
    kind: str
    label: str
    foundry_connection_id: str = ""
    keyvault_ref: str = ""
    min_role_read: str = "Reader"
    min_role_write: str = "Author"
    enabled: bool = True


# Per-tenant config fields that are secrets — redacted from API responses (ADR-005/008).
# (The legacy flat mcp_github_pat predates the connection-reference model; never echo it back.)
_SECRET_CONFIG_FIELDS = ("mcp_github_pat",)


def _redacted(rec: TenantRecord) -> TenantRecord:
    """A copy with secret-bearing data_plane fields blanked — for responses only."""
    return replace(rec, data_plane=replace(rec.data_plane, **{f: "" for f in _SECRET_CONFIG_FIELDS}))


@router.get("", dependencies=[_admin])
def get_tenant(user: User = Security(azure_scheme)):  # type: ignore[arg-type]
    """Record if onboarded, else whether the caller MAY onboard. Tolerates no record."""
    _current_user.set(user)
    rec = _store().get(getattr(user, "tid", None))
    if rec is None:
        return {"onboarded": False, "can_onboard": getattr(user, "tid", None) in settings.allowed_tids}
    return {"onboarded": True, "record": _redacted(rec)}  # never echo secrets


class OnboardBody(BaseModel):
    tier: str | None = None


@router.post("/onboard")
def onboard(body: OnboardBody | None = None, user: User = Depends(onboarding_guard)):
    """Create the tenant record (idempotent). Gated by Admin + allow-list, not resolution.

    Seeds enabled_domains from the tier (ADR-010 Open Q#3); a bodyless POST → tier None →
    "shared" → all domains, identical to before.
    """
    body = body or OnboardBody()
    store = _store()
    tid = getattr(user, "tid", None)
    if store.get(tid) is None:
        tier = body.tier or "shared"
        store.put(TenantRecord(tid=tid, name=tid, tier=tier, status="active",
                               data_plane=TenantConfig(), enabled_domains=domains_for_tier(tier)))
    return {"onboarded": True}


@router.put("/config", dependencies=_user_admin)
def put_config(body: ConfigBody):
    rec = _my_record()
    _store().put(replace(rec, data_plane=replace(rec.data_plane, **body.model_dump())))
    return {"ok": True}


@router.get("/connections", dependencies=_user_admin)
def list_connections():
    return {"connections": list(_my_record().connections)}


@router.post("/connections", dependencies=_user_admin)
def add_connection(body: ConnectionBody):
    if not validate_kind(body.kind):
        raise HTTPException(422, f"unknown kind: {body.kind}")
    if not (body.foundry_connection_id or body.keyvault_ref):
        raise HTTPException(422, "a connection needs foundry_connection_id or keyvault_ref")
    conn = Connection(**body.model_dump())
    _store().put(with_connection(_my_record(), conn))
    return {"ok": True}


@router.delete("/connections/{conn_id}", dependencies=_user_admin)
def delete_connection(conn_id: str):
    _store().put(without_connection(_my_record(), conn_id))
    return {"ok": True}


class DomainsBody(BaseModel):
    enabled: list[str]


@router.get("/domains", dependencies=_user_admin)
def get_domains():
    """The domain catalog + this tenant's entitlement (Admin, tenant-scoped)."""
    return {"catalog": list(DOMAIN_IDS), "enabled": list(_my_record().enabled_domains)}


@router.put("/domains", dependencies=_user_admin)
def put_domains(body: DomainsBody):
    """Tighten/adjust this tenant's domain entitlement. Rejects ids outside the catalog."""
    unknown = [d for d in body.enabled if d not in DOMAIN_IDS]
    if unknown:
        raise HTTPException(422, f"unknown domain(s): {', '.join(unknown)}")
    rec = _my_record()
    enabled = tuple(d for d in DOMAIN_IDS if d in set(body.enabled))   # preserve catalog order, dedupe
    _store().put(replace(rec, enabled_domains=enabled))
    return {"ok": True}


class AreaCreateBody(BaseModel):
    id: UUID
    name: str = Field(min_length=1, max_length=120)
    entra_group_ids: list[UUID] = Field(default_factory=list, max_length=100)


class AreaPatchBody(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=120)
    entra_group_ids: list[UUID] | None = Field(default=None, max_length=100)
    status: Literal["active", "suspended"] | None = None

    @model_validator(mode="after")
    def require_change(self):
        if self.name is None and self.entra_group_ids is None and self.status is None:
            raise ValueError("at least one area field is required")
        return self


def _area(rec: TenantRecord, area_id: str) -> AuthoringArea | None:
    return next((area for area in rec.areas if area.id == area_id), None)


def _set_etag(response: Response, revision: int) -> None:
    response.headers["ETag"] = f'"{revision}"'


def _if_match_revision(value: str) -> int:
    normalized = value.strip()
    if normalized.startswith("W/"):
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "AREA_REVISION_MISMATCH")
    try:
        return int(normalized.strip('"'))
    except ValueError as exc:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "AREA_REVISION_MISMATCH") from exc


@router.get("/areas", dependencies=_user_admin)
def list_areas():
    return {"areas": list(_my_record().areas)}


@router.post("/areas", dependencies=_user_admin, status_code=status.HTTP_201_CREATED)
def create_area(body: AreaCreateBody, response: Response):
    rec = _my_record()
    area_id = str(body.id)
    if _area(rec, area_id) is not None:
        raise HTTPException(status.HTTP_409_CONFLICT, "AREA_ALREADY_EXISTS")

    area = AuthoringArea(
        id=area_id,
        name=body.name,
        entra_group_ids=tuple(dict.fromkeys(str(group_id) for group_id in body.entra_group_ids)),
    )
    _store().put(with_area(rec, area))
    _set_etag(response, area.revision)
    logger.info("authoring_area_created", extra={"tenant_id": rec.tid, "area_id": area.id})
    return {"area": area}


@router.patch("/areas/{area_id}", dependencies=_user_admin)
def patch_area(
    area_id: UUID,
    body: AreaPatchBody,
    response: Response,
    if_match: Annotated[str, Header(alias="If-Match")],
):
    rec = _my_record()
    current = _area(rec, str(area_id))
    if current is None:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "AREA_NOT_FOUND")
    if _if_match_revision(if_match) != current.revision:
        raise HTTPException(status.HTTP_412_PRECONDITION_FAILED, "AREA_REVISION_MISMATCH")

    groups = (
        current.entra_group_ids
        if body.entra_group_ids is None
        else tuple(dict.fromkeys(str(group_id) for group_id in body.entra_group_ids))
    )
    updated = replace(
        current,
        name=body.name if body.name is not None else current.name,
        entra_group_ids=groups,
        status=body.status if body.status is not None else current.status,
        revision=current.revision + 1,
    )
    _store().put(replace_area(rec, updated))
    _set_etag(response, updated.revision)
    logger.info("authoring_area_updated", extra={"tenant_id": rec.tid, "area_id": updated.id})
    return {"area": updated}
