"""HTTP da publicação de revisões aprovadas."""

from __future__ import annotations

import logging
from typing import Annotated
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.modules.authoring.public import ChangeSetScope
from app.modules.publication.public import (
    GitHubPublicationService,
    PublicationConflict,
    PublicationConsentRequired,
    PublicationExternalError,
    PublicationInvalid,
    PublicationNotFound,
    PublicationRequest,
    default_publication_service,
)
from app.modules.tenancy.public import current_area, current_tenant_id, require_area
from app.shared.auth import auth_dependencies, current_roles, current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/authoring/publications",
    tags=["authoring-publication"],
    dependencies=[
        *auth_dependencies(),
        Depends(require_role("Reader", "Author", "Approver", "Admin")),
        Depends(require_area),
    ],
)

PublicationId = Annotated[
    str,
    Path(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    ),
]
IdempotencyKey = Annotated[
    str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
]


class CreatePublicationBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    changeset_id: str = Field(
        min_length=36,
        max_length=36,
        pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$",
    )
    revision: int = Field(ge=1)
    content_hash: str = Field(min_length=64, max_length=64, pattern=r"^[0-9a-f]{64}$")
    owner: str = Field(min_length=1, max_length=100)
    repository: str = Field(min_length=1, max_length=100)
    base_branch: str = Field(default="main", min_length=1, max_length=128)
    target_directory: str = Field(default="okf", min_length=1, max_length=128)


class PublicationApprovalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    approval_id: str = Field(min_length=32, max_length=32, pattern=r"^[0-9a-f]{32}$")
    approved: bool


def _scope() -> ChangeSetScope:
    area = current_area()
    if area is None:
        raise HTTPException(404, "AREA_NOT_FOUND")
    user = current_user()
    return ChangeSetScope(
        current_tenant_id() or "self-hosted",
        area.id,
        getattr(user, "oid", None) or "local-approver",
    )


def _error(exc: Exception) -> JSONResponse:
    if isinstance(exc, PublicationNotFound):
        return JSONResponse(status_code=404, content={"error": {"code": str(exc)}})
    if isinstance(exc, PublicationConflict):
        return JSONResponse(status_code=409, content={"error": {"code": str(exc)}})
    if isinstance(exc, PublicationConsentRequired):
        return JSONResponse(
            status_code=424,
            content={
                "error": {
                    "code": str(exc),
                    "consentUrl": exc.consent_url,
                    "serverLabel": exc.server_label,
                }
            },
            headers={"Cache-Control": "no-store"},
        )
    if isinstance(exc, PublicationExternalError):
        correlation_id = uuid4().hex
        logger.warning(
            "publication external failure correlation_id=%s code=%s",
            correlation_id,
            str(exc),
        )
        return JSONResponse(
            status_code=424,
            content={
                "error": {
                    "code": str(exc),
                    "correlationId": correlation_id,
                }
            },
        )
    if isinstance(exc, PublicationInvalid):
        return JSONResponse(status_code=422, content={"error": {"code": str(exc)}})
    raise exc


@router.post("", response_model=None, dependencies=[Depends(require_role("Approver"))])
async def create_publication(
    body: CreatePublicationBody,
    idempotency_key: IdempotencyKey,
    scope: Annotated[ChangeSetScope, Depends(_scope)],
    service: Annotated[GitHubPublicationService, Depends(default_publication_service)],
) -> JSONResponse:
    try:
        outcome = await service.publish(
            scope,
            PublicationRequest(
                **body.model_dump(),
                idempotency_key=idempotency_key,
            ),
            roles=current_roles(),
        )
        return JSONResponse(
            status_code=200 if outcome.replay else 202,
            content=outcome.to_dict(),
            headers={
                "Cache-Control": "no-store",
                "Idempotent-Replay": str(outcome.replay).lower(),
            },
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.post(
    "/{publication_id}/approvals",
    response_model=None,
    dependencies=[Depends(require_role("Approver"))],
)
async def decide_publication_tool(
    publication_id: PublicationId,
    body: PublicationApprovalBody,
    scope: Annotated[ChangeSetScope, Depends(_scope)],
    service: Annotated[GitHubPublicationService, Depends(default_publication_service)],
) -> JSONResponse:
    try:
        outcome = await service.decide(
            scope,
            publication_id,
            body.approval_id,
            approved=body.approved,
            roles=current_roles(),
        )
        return JSONResponse(
            status_code=200 if outcome.publication.state == "completed" else 202,
            content=outcome.to_dict(),
            headers={"Cache-Control": "no-store"},
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/{publication_id}", response_model=None)
def get_publication(
    publication_id: PublicationId,
    scope: Annotated[ChangeSetScope, Depends(_scope)],
    service: Annotated[GitHubPublicationService, Depends(default_publication_service)],
) -> JSONResponse:
    try:
        publication = service.get(scope, publication_id)
        return JSONResponse(
            status_code=200,
            content=publication.to_dict(),
            headers={"Cache-Control": "no-store"},
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)
