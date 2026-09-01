"""HTTP canônico do catálogo factual de autoria."""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, Header, HTTPException, Path, Query, Response
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field

from app.modules.authoring.public import (
    ChangeSetConflict,
    ChangeSetNotFound,
    ChangeSetPreconditionFailed,
    ChangeSetScope,
    ChangeSetService,
    ResourceNotFound,
    SnapshotStale,
    catalog_page,
    default_changeset_service,
    default_sources,
    resource_activity,
    resource_detail,
    resource_versions,
)
from app.modules.okf.public import AuthoringInvalid
from app.modules.tenancy.public import current_area, current_tenant_id, require_area
from app.shared.auth import auth_dependencies, current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/authoring",
    tags=["authoring-catalog"],
    dependencies=[
        *auth_dependencies(),
        Depends(require_role("Reader", "Author", "Approver", "Admin")),
        Depends(require_area),
    ],
)

CatalogKind = Literal[
    "agent", "knowledge", "skill", "toolbox", "connection", "usecase", "formflow", "copilot"
]
CatalogState = Literal[
    "active", "available", "compatible", "configuration_required", "shadow", "quarantined", "unavailable"
]
ResourceId = Annotated[
    str,
    Path(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$"),
]
ChangeSetId = Annotated[
    str,
    Path(min_length=36, max_length=36, pattern=r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$"),
]
IdempotencyKey = Annotated[str, Header(alias="Idempotency-Key", min_length=8, max_length=128)]
IfMatch = Annotated[str, Header(alias="If-Match", min_length=68, max_length=80)]


class CreateChangeSetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source: Literal["manual", "builder", "import", "migration"]
    base_snapshot_id: str = Field(min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")
    content: dict[str, Any]


class UpdateChangeSetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    content: dict[str, Any]
    base_snapshot_id: str | None = Field(default=None, min_length=1, max_length=128, pattern=r"^[A-Za-z0-9][A-Za-z0-9._:-]*$")


def _scope() -> ChangeSetScope:
    area = current_area()
    if area is None:
        raise HTTPException(404, "AREA_NOT_FOUND")
    user = current_user()
    return ChangeSetScope(
        current_tenant_id() or "self-hosted",
        area.id,
        getattr(user, "oid", None) or "local-author",
    )


def _error(exc: Exception):
    if isinstance(exc, SnapshotStale):
        return JSONResponse(status_code=409, content={"error": {"code": "SNAPSHOT_STALE", "message": "O catálogo mudou; atualize a consulta."}})
    if isinstance(exc, ResourceNotFound):
        raise HTTPException(404, "RESOURCE_NOT_FOUND") from exc
    if isinstance(exc, ChangeSetNotFound):
        raise HTTPException(404, "CHANGESET_NOT_FOUND") from exc
    if isinstance(exc, ChangeSetPreconditionFailed):
        return JSONResponse(status_code=412, content={"error": {"code": "CHANGESET_REVISION_STALE"}})
    if isinstance(exc, ChangeSetConflict):
        return JSONResponse(status_code=409, content={"error": {"code": "IDEMPOTENCY_KEY_REUSED"}})
    if isinstance(exc, AuthoringInvalid):
        raise HTTPException(422, str(exc)) from exc
    correlation_id = uuid4().hex
    logger.error(
        "authoring source unavailable correlation_id=%s",
        correlation_id,
        exc_info=exc,
    )
    return JSONResponse(
        status_code=502,
        content={"error": {"code": "SOURCE_UNAVAILABLE", "message": "A fonte do recurso está indisponível.", "correlationId": correlation_id}},
    )


@router.post(
    "/changesets",
    response_model=None,
    dependencies=[Depends(require_role("Author", "Admin"))],
)
def create_changeset(
    body: CreateChangeSetBody,
    idempotency_key: IdempotencyKey,
    scope: Annotated[ChangeSetScope, Depends(_scope)],
    service: Annotated[ChangeSetService, Depends(default_changeset_service)],
) -> JSONResponse:
    try:
        record, replay = service.create(
            scope,
            source=body.source,
            base_snapshot_id=body.base_snapshot_id,
            content=body.content,
            idempotency_key=idempotency_key,
        )
        return JSONResponse(
            status_code=200 if replay else 201,
            content=record.to_dict(),
            headers={"ETag": record.etag, "Cache-Control": "no-store"},
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/changesets/{changeset_id}", response_model=None)
def get_changeset(
    changeset_id: ChangeSetId,
    scope: Annotated[ChangeSetScope, Depends(_scope)],
    service: Annotated[ChangeSetService, Depends(default_changeset_service)],
) -> Response:
    try:
        record = service.get(scope, changeset_id)
        return JSONResponse(
            status_code=200,
            content=record.to_dict(),
            headers={"ETag": record.etag, "Cache-Control": "no-store"},
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.patch(
    "/changesets/{changeset_id}",
    response_model=None,
    dependencies=[Depends(require_role("Author", "Admin"))],
)
def update_changeset(
    changeset_id: ChangeSetId,
    body: UpdateChangeSetBody,
    if_match: IfMatch,
    scope: Annotated[ChangeSetScope, Depends(_scope)],
    service: Annotated[ChangeSetService, Depends(default_changeset_service)],
) -> Response:
    try:
        record = service.update(
            scope,
            changeset_id,
            expected_etag=if_match,
            content=body.content,
            base_snapshot_id=body.base_snapshot_id,
        )
        return JSONResponse(
            status_code=200,
            content=record.to_dict(),
            headers={"ETag": record.etag, "Cache-Control": "no-store"},
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/catalog", response_model=None)
def catalog(
    kind: CatalogKind | None = None,
    state: CatalogState | None = None,
    cursor: Annotated[str | None, Query(min_length=8, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict | JSONResponse:
    try:
        return catalog_page(
            sources=default_sources(), limit=limit, cursor=cursor, kind=kind, state=state
        )
    except Exception as exc:  # noqa: BLE001 - mapeamento sanitizado da fronteira HTTP
        return _error(exc)


@router.get("/resources/{kind}/{resource_id}", response_model=None)
def detail(kind: CatalogKind, resource_id: ResourceId) -> dict | JSONResponse:
    try:
        return resource_detail(kind, resource_id, sources=default_sources())
    except Exception as exc:  # noqa: BLE001
        return _error(exc)



@router.get("/resources/{kind}/{resource_id}/versions", response_model=None)
def versions(
    kind: CatalogKind,
    resource_id: ResourceId,
    cursor: Annotated[str | None, Query(min_length=8, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict | JSONResponse:
    try:
        return resource_versions(
            kind, resource_id, sources=default_sources(), limit=limit, cursor=cursor
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)


@router.get("/resources/{kind}/{resource_id}/activity", response_model=None)
def activity(
    kind: CatalogKind,
    resource_id: ResourceId,
    cursor: Annotated[str | None, Query(min_length=8, max_length=512)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
) -> dict | JSONResponse:
    try:
        return resource_activity(
            kind, resource_id, sources=default_sources(), limit=limit, cursor=cursor
        )
    except Exception as exc:  # noqa: BLE001
        return _error(exc)
