"""HTTP da trilha de auditoria (ADR-023).

TUDO AQUI EXIGE **Admin**. A trilha diz quem aprovou o quê e quem leu qual documento — é o
retrato de quem faz o quê na empresa, e o dano de expô-la é diferente do de expor um recurso
qualquer. O Diligo permite a leitura da trilha a qualquer membro do tenant; aqui ela é mais
restrita porque o nosso escopo `access` registra leitura de documento por pessoa, que o dele não
registra.

NÃO EXISTE ROTA DE ESCRITA NEM DE APAGAR. Eventos entram pelos módulos que os produzem
(aprovação, acesso, redação), nunca por HTTP — uma rota de escrita transformaria a trilha em algo
que qualquer Admin pode fabricar, e o valor dela é justamente não ser fabricável.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import Response

from app.modules.audit.public import (
    AnchorExists,
    build_package,
    build_report,
    check,
    close_day,
    list_anchors,
    read,
)
from app.shared.auth import auth_dependencies, require_role

router = APIRouter(
    prefix="/audit",
    tags=["audit"],
    dependencies=[*auth_dependencies(), Depends(require_role("Admin"))],
)


def _guard(fn):
    try:
        return fn()
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Auditoria: {exc}") from exc


@router.get("/report")
def report() -> dict:
    """A verificação de todos os escopos, com as provas ausentes declaradas."""
    return _guard(build_report)


@router.get("/trail/{scope}")
def trail_of(scope: str) -> dict:
    """Os eventos de um escopo, com o resultado da reconstrução da cadeia."""
    return _guard(lambda: {"scope": scope, "events": read(scope), "chain": check(scope)})


@router.get("/anchors/{scope}")
def anchors(scope: str) -> dict:
    """Os fechos diários já gravados."""
    return _guard(lambda: {"scope": scope, "anchors": list_anchors(scope)})


@router.post("/anchors/{scope}")
def close(scope: str, date: str = "") -> dict:
    """Fecha o dia: verifica a cadeia e grava a âncora write-once.

    Recusa se a âncora do dia já existir — write-once é o ponto, e sobrescrever seria permitir
    reancorar uma trilha reescrita. Recusa também se a cadeia estiver violada: ancorar uma trilha
    adulterada seria certificá-la.
    """
    try:
        return close_day(scope, date)
    except AnchorExists as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Auditoria: {exc}") from exc


@router.get("/package")
def package() -> Response:
    """O pacote de diligência: trilha + âncoras + verificação + como verificar sem este produto."""
    conteudo = _guard(build_package)
    return Response(
        content=conteudo,
        media_type="application/zip",
        headers={"Content-Disposition": 'attachment; filename="diligencia.zip"'},
    )
