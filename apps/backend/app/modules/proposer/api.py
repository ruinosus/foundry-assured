"""HTTP do propositor.

RASCUNHAR é leitura do catálogo mais uma chamada de modelo — não muda nada, e vale para qualquer
usuário autenticado. DISPARAR uma otimização consome cota do projeto e cria um job, então exige
**Admin**, como as demais operações caras deste produto.

Nenhuma rota aqui publica agente nem promove candidato. Isso é verificado por
`tests/architecture/proposer_read_only_test.py`, não prometido em comentário.
"""

from __future__ import annotations

import logging
from typing import Annotated, Any, Literal

from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request
from pydantic import BaseModel, ConfigDict, Field

from app.modules.authoring.public import (
    ChangeSetScope,
    ChangeSetService,
    catalog_page,
    default_changeset_service,
    default_sources,
)
from app.modules.okf.public import AuthoringInvalid
from app.modules.proposer.public import (
    build_changeset_proposal,
    get_optimization,
    list_optimizations,
    propose_agent,
    review_changeset_proposal,
    start_optimization,
)
from app.modules.tenancy.public import current_area, current_tenant_id, require_area
from app.shared.auth import auth_dependencies, current_user, require_role

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/proposer", tags=["proposer"], dependencies=auth_dependencies())

_admin = [Depends(require_role("Admin"))]


class ChangeSetProposalBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    need: str = Field(min_length=1, max_length=2000)


class ProposalDecisionBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operation_id: str = Field(
        min_length=1, max_length=63, pattern=r"^[a-z0-9][a-z0-9-]*$"
    )
    decision: Literal["accept", "edit", "discard"]
    edited_document: str | None = Field(default=None, max_length=262144)


class ConfirmChangeSetBody(BaseModel):
    model_config = ConfigDict(extra="forbid")

    proposal: dict[str, Any]
    decisions: list[ProposalDecisionBody] = Field(min_length=1, max_length=100)


def _complete_catalog() -> dict[str, Any]:
    page = catalog_page(sources=default_sources(), limit=100)
    items = list(page["items"])
    while page["next_cursor"] is not None:
        page = catalog_page(
            sources=default_sources(), limit=100, cursor=page["next_cursor"]
        )
        items.extend(page["items"])
    return {**page, "items": items, "next_cursor": None}


def _guard(fn):
    """Erro de pedido vira 400; falha de serviço vira 502. Um rascunho ilegível é problema da
    chamada de modelo, e mandar a pessoa procurar no Azure seria mandar para o lugar errado."""
    try:
        return fn()
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Propositor: {exc}") from exc


@router.post("/draft")
async def draft(body: dict, request: Request) -> dict:
    """Rascunha um agente a partir de uma necessidade. NÃO publica — devolve o formulário."""
    need = str(body.get("need") or "")
    # O idioma vem do cabeçalho que o frontend já manda em todo chat — sem isso o rascunho nasce
    # em inglês para quem está usando a tela em português.
    idioma = (request.headers.get("accept-language") or "").split(",")[0]
    try:
        return await propose_agent(need, idioma)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Propositor: {exc}") from exc


@router.post(
    "/changeset",
    dependencies=[Depends(require_role("Author", "Admin")), Depends(require_area)],
)
async def changeset(
    body: ChangeSetProposalBody,
    request: Request,
    area_id: Annotated[str, Header(alias="X-Area-ID")],
) -> dict:
    """Propõe documentos OKF para revisão; não persiste nem publica."""
    area = current_area()
    if area is None or area.id != area_id:
        raise HTTPException(status_code=404, detail="AREA_NOT_FOUND")
    idioma = (request.headers.get("accept-language") or "").split(",")[0]
    try:
        draft_result = await propose_agent(body.need, idioma)
        catalog = _complete_catalog()
        user = current_user()
        result = build_changeset_proposal(
            draft_result,
            catalog,
            tenant_id=current_tenant_id() or "self-hosted",
            area_id=area.id,
            actor_id=getattr(user, "oid", None) or "local-author",
        )
        logger.info(
            "builder proposal snapshot_id=%s operations=%s result=%s",
            result["snapshot"]["id"],
            len(result["proposal"]["operations"]) if result["proposal"] else 0,
            "proposed" if result["proposal"] else "gap",
        )
        return result
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("builder proposal failed")
        raise HTTPException(status_code=502, detail="PROPOSER_UNAVAILABLE") from exc


@router.post(
    "/changeset/confirm",
    dependencies=[Depends(require_role("Author", "Admin")), Depends(require_area)],
)
def confirm_changeset(
    body: ConfirmChangeSetBody,
    area_id: Annotated[str, Header(alias="X-Area-ID")],
    idempotency_key: Annotated[
        str, Header(alias="Idempotency-Key", min_length=8, max_length=128)
    ],
    service: Annotated[ChangeSetService, Depends(default_changeset_service)],
) -> dict:
    """Revalida e persiste exatamente um ChangeSet; ainda não publica recursos."""
    area = current_area()
    if area is None or area.id != area_id:
        raise HTTPException(status_code=404, detail="AREA_NOT_FOUND")
    user = current_user()
    tenant_id = current_tenant_id() or "self-hosted"
    actor_id = getattr(user, "oid", None) or "local-author"
    try:
        reviewed = review_changeset_proposal(
            body.proposal,
            [decision.model_dump() for decision in body.decisions],
            _complete_catalog(),
            tenant_id=tenant_id,
            area_id=area.id,
        )
        record, replay = service.create(
            ChangeSetScope(tenant_id, area.id, actor_id),
            source="builder",
            base_snapshot_id=str(reviewed["base_version"]),
            content=reviewed,
            idempotency_key=idempotency_key,
        )
        logger.info(
            "builder changeset confirmed changeset_id=%s revision=%s replay=%s",
            record.id,
            record.revision,
            replay,
        )
        return record.to_dict()
    except AuthoringInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("builder changeset confirmation failed")
        raise HTTPException(status_code=502, detail="CHANGESET_CONFIRMATION_FAILED") from exc


@router.get("/optimizations")
def optimizations(limit: int = Query(20, ge=1, le=100)) -> dict:
    """Os jobs de otimização do projeto."""
    return {"jobs": _guard(lambda: list_optimizations(limit))}


@router.get("/optimizations/{job_id}")
def optimization(job_id: str) -> dict:
    """Um job com seus candidatos pontuados, melhor nota primeiro."""
    return _guard(lambda: get_optimization(job_id))


@router.post("/optimizations", dependencies=_admin)
def start(body: dict) -> dict:
    """Dispara uma otimização. Cria um job no projeto; NÃO promove candidato nenhum."""
    return _guard(
        lambda: start_optimization(
            str(body.get("agent") or ""),
            str(body.get("version") or ""),
            body.get("train_dataset") or {},
            body.get("evaluators") or [],
        )
    )
