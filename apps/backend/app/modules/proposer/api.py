"""HTTP do propositor.

RASCUNHAR é leitura do catálogo mais uma chamada de modelo — não muda nada, e vale para qualquer
usuário autenticado. DISPARAR uma otimização consome cota do projeto e cria um job, então exige
**Admin**, como as demais operações caras deste produto.

Nenhuma rota aqui publica agente nem promove candidato. Isso é verificado por
`tests/architecture/proposer_read_only_test.py`, não prometido em comentário.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request

from app.modules.proposer.public import (
    get_optimization,
    list_optimizations,
    propose_agent,
    start_optimization,
)
from app.shared.auth import auth_dependencies, require_role

router = APIRouter(prefix="/proposer", tags=["proposer"], dependencies=auth_dependencies())

_admin = [Depends(require_role("Admin"))]


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
