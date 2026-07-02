"""Per-tenant management API (shared mode) — config + connections, Admin-gated + tenant-scoped.

GET /tenant uses require_role("Admin") ALONE (it must tolerate a not-yet-onboarded tenant —
require_user would resolve the tenant and 403). The config/connection endpoints use require_user
(they require an onboarded tenant) + Admin. Every write is a read-modify-write of the caller's
own record (current_tenant_id()); no tid comes from the path. See the sub-project B design.
"""

from __future__ import annotations

from dataclasses import replace

from fastapi import APIRouter, Depends, HTTPException, Security
from fastapi_azure_auth.user import User
from pydantic import BaseModel

from app.core import auth as _auth
from app.core.auth import _current_user, azure_scheme, require_role, require_user
from app.core.onboarding import onboarding_guard
from app.core.settings import settings
from app.core.tenant import TenantConfig, current_tenant_id, DOMAIN_IDS, domains_for_tier
from app.core.tenant_store import (
    Connection, TenantRecord, validate_kind, with_connection, without_connection,
)

router = APIRouter(prefix="/tenant", tags=["tenant"])
_admin = Depends(require_role("Admin"))
_user_admin = [Depends(require_user), Depends(require_role("Admin"))]


def _store():
    if _auth._tenant_store is None:
        raise HTTPException(503, "tenant store unavailable")
    return _auth._tenant_store


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
