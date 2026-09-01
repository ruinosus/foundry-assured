"""HTTP canônico do catálogo factual de autoria."""

from __future__ import annotations

import logging
from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Path, Query
from fastapi.responses import JSONResponse

from app.modules.authoring.public import (
    ResourceNotFound,
    SnapshotStale,
    catalog_page,
    default_sources,
    resource_activity,
    resource_detail,
    resource_versions,
)
from app.modules.okf.public import AuthoringInvalid
from app.modules.tenancy.public import require_area
from app.shared.auth import auth_dependencies, require_role

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


def _error(exc: Exception):
    if isinstance(exc, SnapshotStale):
        return JSONResponse(409, {"error": {"code": "SNAPSHOT_STALE", "message": "O catálogo mudou; atualize a consulta."}})
    if isinstance(exc, ResourceNotFound):
        raise HTTPException(404, "RESOURCE_NOT_FOUND") from exc
    if isinstance(exc, AuthoringInvalid):
        raise HTTPException(422, str(exc)) from exc
    correlation_id = uuid4().hex
    logger.error(
        "authoring source unavailable correlation_id=%s",
        correlation_id,
        exc_info=exc,
    )
    return JSONResponse(
        502,
        {"error": {"code": "SOURCE_UNAVAILABLE", "message": "A fonte do recurso está indisponível.", "correlationId": correlation_id}},
    )


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
