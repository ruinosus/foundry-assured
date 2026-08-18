"""HTTP das conversas — listar as minhas, e reabrir uma.

Não há parâmetro de usuário em nenhuma rota, e isso é o controle de acesso: o dono é sempre quem
está autenticado, lido do token. Um `?user=` seria um IDOR pronto — bastaria trocar o id na URL
para ler a conversa de outra pessoa.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.modules.conversations.public import (
    conversation_user,
    find_conversation,
    get_conversation,
    list_conversations,
)
from app.shared.auth import auth_dependencies

router = APIRouter(
    prefix="/conversations", tags=["conversations"], dependencies=auth_dependencies()
)


@router.get("")
def listar(agent: str = Query("", description="Filtra por agente/domínio")) -> dict:
    """As conversas do usuário autenticado, mais recentes primeiro."""
    try:
        return {"conversations": list_conversations(conversation_user(), agent)}
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Conversas: {exc}") from exc


@router.get("/by-id/{conversation_id}")
def por_id(conversation_id: str) -> dict:
    """A conversa pelo ID, sem o agente — é o que o `connect` do CopilotKit consegue informar.

    Rota separada e ANTES da rota com agente: `/by-id/x` casaria com `/{agent}/{conversation_id}`
    se viesse depois, e o FastAPI resolve na ordem de declaração.
    """
    achada = _guard_find(conversation_id)
    if not achada:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"id": conversation_id, **achada}


def _guard_find(conversation_id: str) -> dict:
    try:
        return find_conversation(conversation_user(), conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Conversas: {exc}") from exc


@router.get("/{agent}/{conversation_id}")
def abrir(agent: str, conversation_id: str) -> dict:
    """As mensagens de uma conversa, para reabri-la na tela."""
    try:
        mensagens = get_conversation(conversation_user(), agent, conversation_id)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Conversas: {exc}") from exc

    # Conversa vazia é 404: pode ser id errado ou de outra pessoa, e as duas respostas devem ser
    # iguais — dizer "existe mas não é sua" já vazaria a existência.
    if not mensagens:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"id": conversation_id, "agent": agent, "messages": mensagens}
