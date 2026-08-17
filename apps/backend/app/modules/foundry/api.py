"""HTTP para os recursos do Foundry.

Leitura exige apenas autenticação: ver o catálogo é o passo que traz o usuário para dentro.
Escrita (quando existir) exigirá Admin, porque criar agente e apagar base mudam o que as
outras pessoas veem.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.modules.foundry.public import get_agent, list_agents
from app.shared.auth import auth_dependencies

router = APIRouter(prefix="/foundry", tags=["foundry"], dependencies=auth_dependencies())


def _guard(fn):
    """Falha do SDK/serviço vira HTTP legível.

    Sem isto, um projeto sem agentes ou uma credencial sem permissão chega ao browser como 500
    mudo — o mesmo defeito que /admin/users tinha e que custou uma hora para diagnosticar.
    """
    try:
        return fn()
    except HTTPException:
        raise
    except Exception as exc:  # noqa: BLE001 — a mensagem do serviço é o que ajuda quem opera
        raise HTTPException(status_code=502, detail=f"Foundry: {exc}") from exc


@router.get("/agents")
def agents(limit: int = Query(50, ge=1, le=100)) -> dict:
    return {"agents": _guard(lambda: list_agents(limit))}


@router.get("/agents/{name}")
def agent(name: str) -> dict:
    return _guard(lambda: get_agent(name))
