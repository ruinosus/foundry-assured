"""Authoring HTTP para projeção Foundry e discovery administrativa MCP."""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field

from app.modules.foundry.public import list_toolbox_projection
from app.modules.okf.public import AuthoringInvalid
from app.modules.platform_ops.public import (
    ConformityNotFound,
    DiscoveryRejected,
    discover_toolbox,
    evaluate_mcp_binding,
    get_snapshot,
)
from app.shared.auth import auth_dependencies, require_role

router = APIRouter(prefix="/authoring", tags=["authoring"], dependencies=auth_dependencies())
_admin = [Depends(require_role("Admin"))]


class ToolboxSource(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=63)
    version: str = Field(min_length=1, max_length=64)


class DiscoveryBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    toolbox: ToolboxSource


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
    responses={400: {}, 422: {}, 502: {}},
)
async def discover(body: DiscoveryBody) -> dict:
    try:
        return await discover_toolbox(body.toolbox.name, body.toolbox.version)
    except DiscoveryRejected as exc:
        raise HTTPException(422, str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Discovery MCP não pôde ser concluída.") from exc


@router.get("/mcp-snapshots/{snapshot_id}", responses={404: {}})
def snapshot(snapshot_id: str) -> dict:
    result = get_snapshot(snapshot_id)
    if result is None:
        raise HTTPException(404, "Snapshot não encontrado.")
    return result


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
        raise HTTPException(404, "Fonte MCP não encontrada.") from exc
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    except Exception as exc:
        raise HTTPException(502, "Conformidade MCP não pôde ser avaliada.") from exc
