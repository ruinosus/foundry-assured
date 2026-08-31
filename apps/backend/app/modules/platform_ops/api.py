"""Authoring HTTP para projeção Foundry e discovery administrativa MCP."""

from __future__ import annotations

from typing import Annotated, Literal
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.modules.foundry.public import list_toolbox_projection
from app.modules.okf.public import AuthoringInvalid
from app.modules.platform_ops.public import (
    ClassificationConflict,
    ClassificationInvalid,
    ClassificationNotFound,
    ConformityNotFound,
    DiscoveryBusy,
    DiscoveryLimitExceeded,
    DiscoveryRejected,
    EgressDenied,
    EndpointConflict,
    EndpointInvalid,
    SnapshotReviewConflict,
    SnapshotReviewInvalid,
    SnapshotReviewNotFound,
    approve_mcp_endpoint,
    classify_mcp_tool,
    create_mcp_endpoint,
    discover_endpoint,
    discover_toolbox,
    evaluate_mcp_binding,
    get_mcp_source,
    get_snapshot,
    list_mcp_endpoints,
    project_snapshot_classifications,
    review_mcp_snapshot,
)
from app.shared.auth import auth_dependencies, require_role

router = APIRouter(prefix="/authoring", tags=["authoring"], dependencies=auth_dependencies())
_admin = [Depends(require_role("Admin"))]
_SNAPSHOT_NOT_FOUND = "Snapshot não encontrado."
_SOURCE_NOT_FOUND = "Fonte MCP não encontrada."
_DISCOVERY_ERRORS = {
    "MCP_SOURCE_NOT_FOUND": (404, _SOURCE_NOT_FOUND, False),
    "MCP_ENDPOINT_NOT_APPROVED": (409, "Endpoint MCP não aprovado.", False),
    "MCP_DISCOVERY_LIMIT_EXCEEDED": (413, "Resposta MCP excedeu os limites permitidos.", False),
    "MCP_EGRESS_DENIED": (422, "Origem MCP não permitida.", False),
    "MCP_PROTOCOL_INVALID": (422, "Resposta MCP inválida.", False),
    "MCP_AUTH_FAILED": (424, "Autenticação MCP falhou.", False),
    "MCP_DISCOVERY_BUSY": (429, "Já existe uma discovery MCP em andamento.", True),
    "MCP_SOURCE_UNAVAILABLE": (502, "Fonte MCP indisponível.", True),
    "MCP_DISCOVERY_TIMEOUT": (504, "Discovery MCP excedeu o tempo permitido.", True),
}


class ToolboxSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=63)
    version: str = Field(min_length=1, max_length=64)


class DiscoveryBody(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    toolbox: ToolboxSource | None = None
    endpoint_id: str | None = Field(
        default=None, alias="endpointId", pattern=r"^mep_[a-f0-9]{32}$"
    )

    @model_validator(mode="after")
    def one_source(self):
        if (self.toolbox is None) == (self.endpoint_id is None):
            raise ValueError("Informe exatamente uma origem MCP.")
        return self


class EndpointAuth(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    mode: str
    connection_ref: str | None = Field(default=None, alias="connectionRef")


class EndpointBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    url: str = Field(min_length=1, max_length=2048)
    auth: EndpointAuth


class ApprovalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    decision: str
    reason: str = Field(min_length=1, max_length=500)


class ClassificationBody(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    effect: Literal["read", "write"]
    reason: str = Field(min_length=1, max_length=500)
    expected_revision: int = Field(alias="expectedRevision", ge=0)


class SnapshotReviewBody(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)

    reason: str = Field(min_length=1, max_length=500)
    expected_revision: int = Field(alias="expectedRevision", ge=1)


@router.post("/mcp-endpoints", status_code=201, responses={422: {}})
def create_endpoint(body: EndpointBody) -> dict:
    try:
        return create_mcp_endpoint(body.model_dump(by_alias=True, exclude_none=True))
    except EndpointInvalid as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/mcp-endpoints")
def endpoints() -> dict:
    return {"items": list_mcp_endpoints()}


@router.post(
    "/mcp-endpoints/{endpoint_id}/approval",
    dependencies=_admin,
    responses={404: {}, 409: {}, 422: {}},
)
def approve_endpoint(endpoint_id: str, body: ApprovalBody) -> dict:
    try:
        return approve_mcp_endpoint(
            endpoint_id,
            decision=body.decision,
            reason=body.reason,
        )
    except LookupError as exc:
        raise HTTPException(404, "Endpoint MCP não encontrado.") from exc
    except EndpointConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except EndpointInvalid as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/toolboxes", responses={400: {}, 502: {}})
def toolboxes(
    limit: Annotated[int, Query(ge=1, le=100)] = 50,
    cursor: str | None = None,
) -> dict:
    try:
        return list_toolbox_projection(limit, cursor)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Não foi possível consultar as Toolboxes.") from exc


@router.post(
    "/mcp-discoveries",
    status_code=201,
    dependencies=_admin,
    response_model=None,
    responses={404: {}, 409: {}, 413: {}, 422: {}, 424: {}, 429: {}, 502: {}, 504: {}},
)
async def discover(body: DiscoveryBody) -> dict | JSONResponse:
    try:
        if body.endpoint_id is not None:
            return await discover_endpoint(body.endpoint_id)
        toolbox = body.toolbox
        if toolbox is None:
            raise HTTPException(422, "Informe exatamente uma origem MCP.")
        return await discover_toolbox(toolbox.name, toolbox.version)
    except Exception as exc:  # noqa: BLE001 - fronteira HTTP deve falhar fechada e sem detalhe
        return _discovery_error(exc)


def _discovery_error(exc: Exception) -> JSONResponse:
    code = "MCP_SOURCE_UNAVAILABLE"
    if isinstance(exc, TimeoutError):
        code = "MCP_DISCOVERY_TIMEOUT"
    elif isinstance(exc, DiscoveryBusy):
        code = "MCP_DISCOVERY_BUSY"
    elif isinstance(exc, DiscoveryLimitExceeded):
        code = "MCP_DISCOVERY_LIMIT_EXCEEDED"
    elif isinstance(exc, DiscoveryRejected):
        code = "MCP_PROTOCOL_INVALID"
    elif isinstance(exc, EgressDenied):
        internal_code = str(exc)
        code = {
            "MCP_SOURCE_NOT_FOUND": "MCP_SOURCE_NOT_FOUND",
            "MCP_ENDPOINT_NOT_APPROVED": "MCP_ENDPOINT_NOT_APPROVED",
            "MCP_AUTH_NOT_AVAILABLE": "MCP_AUTH_FAILED",
        }.get(internal_code, "MCP_EGRESS_DENIED")
    elif isinstance(exc, ValueError):
        code = "MCP_SOURCE_NOT_FOUND"
    status, message, retryable = _DISCOVERY_ERRORS[code]
    return JSONResponse(
        status_code=status,
        content={
            "error": {
                "code": code,
                "message": message,
                "correlationId": uuid4().hex,
                "retryable": retryable,
            }
        },
    )


@router.get("/mcp-snapshots/{snapshot_id}", responses={404: {}})
def snapshot(snapshot_id: str) -> dict:
    result = get_snapshot(snapshot_id)
    if result is None:
        raise HTTPException(404, _SNAPSHOT_NOT_FOUND)
    try:
        return project_snapshot_classifications(snapshot_id, result)
    except ClassificationNotFound as exc:
        raise HTTPException(404, _SNAPSHOT_NOT_FOUND) from exc


@router.get("/mcp-sources/{source_id}", responses={404: {}})
def source(source_id: str) -> dict:
    result = get_mcp_source(source_id)
    if result is None:
        raise HTTPException(404, _SOURCE_NOT_FOUND)
    return result


@router.post(
    "/mcp-snapshots/{snapshot_id}/review",
    dependencies=_admin,
    responses={404: {}, 409: {}, 422: {}},
)
def review_snapshot(snapshot_id: str, body: SnapshotReviewBody) -> dict:
    try:
        return review_mcp_snapshot(
            snapshot_id,
            reason=body.reason,
            expected_revision=body.expected_revision,
        )
    except SnapshotReviewNotFound as exc:
        raise HTTPException(404, _SNAPSHOT_NOT_FOUND) from exc
    except SnapshotReviewConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except SnapshotReviewInvalid as exc:
        raise HTTPException(422, str(exc)) from exc


@router.put(
    "/mcp-snapshots/{snapshot_id}/tools/{tool_name}/classification",
    dependencies=_admin,
    responses={404: {}, 409: {}, 422: {}},
)
def classify_tool(
    snapshot_id: str, tool_name: str, body: ClassificationBody
) -> dict:
    try:
        return classify_mcp_tool(
            snapshot_id,
            tool_name,
            effect=body.effect,
            reason=body.reason,
            expected_revision=body.expected_revision,
        )
    except ClassificationNotFound as exc:
        raise HTTPException(404, "Snapshot ou tool não encontrado.") from exc
    except ClassificationConflict as exc:
        raise HTTPException(409, str(exc)) from exc
    except ClassificationInvalid as exc:
        raise HTTPException(422, str(exc)) from exc


@router.post(
    "/mcp-bindings/conformity",
    responses={404: {}, 422: {}, 502: {}},
)
def conformity(body: dict) -> dict:
    try:
        return evaluate_mcp_binding(body)
    except AuthoringInvalid as exc:
        raise HTTPException(422, str(exc)) from exc
    except ConformityNotFound as exc:
        raise HTTPException(404, _SOURCE_NOT_FOUND) from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Conformidade MCP não pôde ser avaliada.") from exc
