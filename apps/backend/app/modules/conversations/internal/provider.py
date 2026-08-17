"""O histórico entra no agente pelo seam do próprio framework, não por gambiarra nossa.

`HistoryProvider` é classe base do `agent_framework` (`_sessions.py`) feita exatamente para isto:
o agente chama `before_run` para carregar o histórico no contexto e `after_run` para gravar o que
entrou e o que saiu. Subclasse implementa DUAS funções — `get_messages` e `save_messages` — e
ganha de graça o resto: filtro de mensagens de controle de aprovação, escolha do que persistir
(entrada, saída, contexto de outros providers) e a ordem correta em relação aos outros providers.

Capturar mensagem no laço de SSE, que era a alternativa, veria o texto já serializado em evento
AG-UI e perderia papel, tool call e anexo — além de precisar de um ramo por domínio. Aqui é um
provider só, plugado onde a memória já é plugada (`context_providers=[…]`).

Os built-ins do framework — `InMemoryHistoryProvider` e `FileHistoryProvider` — resolvem processo
único e disco local; nenhum dos dois sobrevive a um container que reinicia. Esta subclasse troca
só o meio de armazenamento, que é a lacuna real.
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any

from agent_framework import HistoryProvider, Message

from app.modules.conversations.internal.store import store

logger = logging.getLogger(__name__)


class StoredHistoryProvider(HistoryProvider):
    """Histórico persistido por usuário, por agente e por conversa.

    POR QUE A CONVERSA VEM AMARRADA e não do `session_id` que o framework passa. `AgentSession`
    gera `str(uuid.uuid4())` quando ninguém informa um id (`_sessions.py`), e quem invoca o agente
    dentro do workflow não informa. O histórico então nunca acumularia: cada turno gravaria sob um
    id novo, e a conversa anterior não seria encontrada — sem erro nenhum, só uma tela que sempre
    começa do zero.

    O `threadId` do AG-UI é o identificador real da conversa, e ele já chega na fábrica do
    workflow. É ele que amarra. O `session_id` do framework continua sendo aceito como reserva,
    para o caso de um chamador que de fato o controle.
    """

    def __init__(
        self,
        user_id: str,
        agent: str,
        conversation_id: str = "",
        *,
        source_id: str = "conversation_history",
    ):
        super().__init__(source_id)
        self._user = user_id
        self._agent = agent
        self._conversation = conversation_id

    def _conv(self, session_id: str | None) -> str:
        return self._conversation or (session_id or "")

    async def get_messages(
        self, session_id: str | None, *, state: dict[str, Any] | None = None, **kwargs: Any
    ) -> list[Message]:
        conversa = self._conv(session_id)
        if not conversa:
            return []
        try:
            linhas = await asyncio.to_thread(store().read, self._user, self._agent, conversa)
        except Exception:
            # Histórico ilegível NÃO derruba a conversa: o usuário perde o contexto anterior, não
            # a capacidade de conversar. Mas o erro sobe no log, porque perder histórico em
            # silêncio é como o painel de ROI acabou contando zero por meses.
            logger.exception("falha ao ler o histórico da conversa %s", conversa)
            return []
        return [Message.from_dict(linha) for linha in linhas]

    async def save_messages(
        self,
        session_id: str | None,
        messages,
        *,
        state: dict[str, Any] | None = None,
        **kwargs: Any,
    ) -> None:
        conversa = self._conv(session_id)
        if not conversa or not messages:
            return
        payload = [m.to_dict() for m in messages]
        try:
            await asyncio.to_thread(
                store().append, self._user, self._agent, conversa, payload
            )
        except Exception:
            # Idem: falhar a gravação não pode abortar a resposta que o usuário já está lendo.
            logger.exception("falha ao gravar o histórico da conversa %s", conversa)


def build_history_provider(
    user_id: str, agent: str, conversation_id: str = ""
) -> StoredHistoryProvider | None:
    """O provider, ou None quando não há usuário autenticado.

    Sem identidade não há onde guardar: gravar conversa sob um usuário anônimo compartilhado
    misturaria o histórico de pessoas diferentes, que é vazamento, não conveniência.
    """
    if not user_id:
        return None
    return StoredHistoryProvider(user_id, agent, conversation_id)
