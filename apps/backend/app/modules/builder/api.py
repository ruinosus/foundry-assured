"""HTTP do assistente de tela.

Registrar o desfecho de uma proposta vale para QUALQUER usuário autenticado — é ele quem decide,
e exigir papel aqui faria a medição existir só para administradores, que são justamente quem menos
usa o wizard. Ler as estatísticas exige **Admin**: é medição de uso por pessoa, e agregado ou não,
ele diz quem está usando o quê.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from app.modules.builder.public import DESFECHOS, InvalidOutcome, record_proposal, stats
from app.shared.auth import auth_dependencies, require_role

router = APIRouter(prefix="/builder-assist", tags=["builder"], dependencies=auth_dependencies())


@router.post("/proposals")
def proposal(body: dict) -> dict:
    """O desfecho de uma proposta: aceita, editada ou descartada.

    A porta é ESTREITA de propósito: tipo e escopo do evento são fixos no servidor e o desfecho
    vem de uma lista fechada. Uma rota que aceitasse evento arbitrário deixaria a trilha
    fabricável por quem tem token.
    """
    try:
        return record_proposal(
            resource=str(body.get("resource") or ""),
            field=str(body.get("field") or ""),
            outcome=str(body.get("outcome") or ""),
            sources=[str(s) for s in (body.get("sources") or [])],
            chars=int(body.get("chars") or 0),
        )
    except InvalidOutcome as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Assistente: {exc}") from exc


@router.get("/stats", dependencies=[Depends(require_role("Admin"))])
def assist_stats() -> dict:
    """Aproveitamento, edição e distribuição por campo — lidos da trilha, sem contador paralelo."""
    try:
        return {"outcomes": list(DESFECHOS), **stats()}
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Assistente: {exc}") from exc
