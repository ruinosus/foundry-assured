"""HTTP das conversas — listar as minhas, reabrir uma, e compartilhar/revogar.

Não há parâmetro de usuário em nenhuma rota, e isso é o controle de acesso: o dono é sempre quem
está autenticado, lido do token. Um `?user=` seria um IDOR pronto — bastaria trocar o id na URL
para ler a conversa de outra pessoa.

A ÚNICA EXCEÇÃO DELIBERADA é `por_id` (usada pelo `connect` do CopilotKit para reidratar a tela):
quando a conversa não é do usuário autenticado, ela tenta o caminho de COMPARTILHADA — explícito
e separado, nunca uma relaxação do filtro por dono (ver o comentário na própria função).
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.modules.conversations.public import (
    conversation_user,
    find_conversation,
    get_conversation,
    is_shared,
    list_conversations,
    read_shared_conversation,
    share_conversation,
    unshare_conversation,
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

    DUAS TENTATIVAS, NUNCA UMA RELAXAÇÃO DA PRIMEIRA. `_guard_find` continua sendo exatamente o
    que já era — filtra pelo usuário autenticado, sem mudar uma linha. Só quando ela devolve
    vazio (não é minha, ou não existe) é que `read_shared_conversation` entra, e é um caminho
    TOTALMENTE separado: consulta o índice de compartilhamento, não a posse. Isto é o que o
    pedido exige — nunca afrouxar o filtro de dono, só somar um segundo, explícito.
    """
    achada = _guard_find(conversation_id)
    if achada:
        return {"id": conversation_id, "shared": False, **achada}

    compartilhada = read_shared_conversation(conversation_id)
    if not compartilhada:
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"id": conversation_id, "shared": True, **compartilhada}


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


@router.get("/{agent}/{conversation_id}/share")
def status_compartilhamento(agent: str, conversation_id: str) -> dict:
    """Se a conversa está compartilhada agora — o que a tela usa para desenhar o botão."""
    return {"shared": is_shared(agent, conversation_id)}


@router.post("/{agent}/{conversation_id}/share")
def compartilhar(agent: str, conversation_id: str) -> dict:
    """Liga o compartilhamento. Só o dono (`share_conversation` confirma a posse por dentro)."""
    if not share_conversation(conversation_user(), agent, conversation_id):
        raise HTTPException(status_code=404, detail="Conversa não encontrada.")
    return {"shared": True}


@router.delete("/{agent}/{conversation_id}/share")
def revogar_compartilhamento(agent: str, conversation_id: str) -> dict:
    """Desliga. Idem: só quem compartilhou consegue revogar."""
    if not unshare_conversation(conversation_user(), agent, conversation_id):
        raise HTTPException(status_code=404, detail="Compartilhamento não encontrado.")
    return {"shared": False}
