"""HTML Artifacts API — generate, list, view, and govern AI-generated HTML.

Thin router: HTTP + RBAC only; logic lives in app/services/artifacts.py.
Tenant partition comes from app.core.tenant.artifact_tenant_id().
"""
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import BaseModel

from app.core.auth import current_user, require_role
from app.core.tenant import artifact_tenant_id
from app.services import artifacts as svc

router = APIRouter(prefix="/artifacts", tags=["artifacts"])

_author = Depends(require_role("Author", "Admin"))
_approver = Depends(require_role("Approver", "Admin"))
_reader = Depends(require_role("Reader", "Author", "Approver", "Admin"))


class GenerateBody(BaseModel):
    title: str
    description: str = ""
    type: str = "report"
    prompt: str


def _dto(rec) -> dict:
    return {
        "id": rec.id, "title": rec.title, "description": rec.description,
        "type": rec.type, "status": rec.status, "createdBy": rec.created_by,
        "createdAt": rec.created_at, "updatedAt": rec.updated_at,
        "approvedBy": rec.approved_by, "approvedAt": rec.approved_at,
        "version": rec.version, "contentHash": rec.content_hash,
    }


@router.post("/html/generate", dependencies=[_author])
async def generate_route(body: GenerateBody) -> dict:
    try:
        rec = await svc.generate(
            tenant_id=artifact_tenant_id(), title=body.title,
            description=body.description, type=body.type, prompt=body.prompt,
            user=current_user(),
        )
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return _dto(rec)


@router.get("/html", dependencies=[_reader])
def list_route() -> dict:
    recs = svc.list_artifacts(artifact_tenant_id())
    return {"artifacts": [_dto(r) for r in recs]}


@router.get("/html/{artifact_id}", dependencies=[_reader])
def get_route(artifact_id: str) -> dict:
    try:
        rec = svc.get_artifact(artifact_tenant_id(), artifact_id, user=current_user())
    except svc.Forbidden:
        raise HTTPException(status_code=404, detail="not found")
    return _dto(rec)


@router.get("/html/{artifact_id}/content", dependencies=[_reader])
def content_route(artifact_id: str) -> Response:
    try:
        html = svc.get_content(artifact_tenant_id(), artifact_id, user=current_user())
    except svc.Forbidden:
        raise HTTPException(status_code=404, detail="not found")
    # Returned to the proxy, which hands it to the frontend for srcdoc injection.
    # NEVER rendered same-origin — the frontend puts it in a sandboxed iframe.
    # Defense-in-depth: `Content-Security-Policy: sandbox` makes the browser
    # sandbox the content even on a direct same-origin navigation — this closes
    # the local-dev gap where auth_enabled=False makes require_role a no-op.
    return Response(
        content=html,
        media_type="text/html",
        headers={
            "Content-Security-Policy": "sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
