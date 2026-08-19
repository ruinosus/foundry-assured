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


def _colapsar_reconstrucoes_duplicadas(mensagens: list[Message]) -> list[Message]:
    """Descarta a reconstrução SEM id de uma resposta que já tem uma reconstrução COM id.

    O QUE FOI MEDIDO, contra uma conversa real do `selfwiki` (blob `bb82ca58-…`, com
    `GROUNDED_VIA_FRAMEWORK=true`, que fala com o `FoundryAgent` publicado): cada turno gravava a
    resposta do assistente DUAS vezes — uma `Message` sem `message_id`, com `author_name` e um
    `text_reasoning` vazio, e outra `Message` com `message_id` real, só com `text` — e as duas
    carregavam o MESMO texto, byte a byte. Não são duas respostas: são duas reconstruções da MESMA
    resposta em streaming (`AgentResponse.from_updates`, a partir das atualizações acumuladas
    localmente, e `stream.get_final_response()`, a partir do objeto final do serviço), e o
    `HistoryProvider.after_run()` do framework grava tudo que estiver em `response.messages` sem
    saber que as duas são a mesma coisa.

    POR QUE FICA A COM ID, e não a outra. Sem `message_id` uma mensagem nunca entra em
    `_ja_gravados` — o reenvio da thread inteira (comportamento do caminho AG-UI, documentado
    acima) a trataria como nova em TODO turno seguinte, e a duplicata cresceria sem fim em vez de
    ficar em uma cópia. A reconstrução sem id não carrega nada que a outra não tenha: o
    `text_reasoning` medido vem sempre vazio, e o `author_name` é metadado, não conteúdo.

    Só colapsa quando o texto bate e não é vazio — coincidência de duas respostas vazias não deve
    apagar uma resposta real por engano.
    """
    com_id = {
        m.text
        for m in mensagens
        if getattr(m, "role", "") == "assistant" and getattr(m, "message_id", None) and m.text
    }
    return [
        m
        for m in mensagens
        if not (
            getattr(m, "role", "") == "assistant"
            and not getattr(m, "message_id", None)
            and m.text
            and m.text in com_id
        )
    ]


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
        #: Os ids que ESTA requisição já encontrou gravados. Preenchido no `get_messages` e lido no
        #: `save_messages` — ver o porquê lá embaixo.
        self._ja_gravados: set[str] = set()

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
        mensagens = [Message.from_dict(linha) for linha in linhas]
        # Guarda os ids do que JÁ está no store. O `save_messages` usa isso para não regravar.
        self._ja_gravados = {
            i for i in (getattr(m, "message_id", None) for m in mensagens) if i
        }
        return mensagens

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

        # DEDUPLICAÇÃO POR ID, e sem I/O extra: os ids vêm do `get_messages` desta mesma execução.
        #
        # POR QUE É NECESSÁRIA. O framework passa para cá `input_messages + response.messages`, e no
        # caminho AG-UI o `input_messages` é a THREAD INTEIRA — o cliente reenvia toda a conversa a
        # cada turno. Como este store é append-only (JSONL), cada turno regravava tudo. Medido numa
        # conversa real de três perguntas: doze mensagens gravadas onde deviam ser seis, com a
        # primeira pergunta aparecendo três vezes.
        #
        # E o estrago não era só tamanho: o histórico duplicado volta como CONTEXTO do agente, e
        # quem procura "a última pergunta do usuário" nele encontra uma pergunta antiga. Foi o que
        # fez a recuperação buscar documentos da pergunta errada.
        #
        # Com sessão própria o framework passa só o turno novo (verificado), então isto é
        # específico do caminho AG-UI — e é aqui que ele tem de ser resolvido, porque é o único
        # ponto que sabe o que já está gravado.
        novas = [
            m
            for m in messages
            if not (getattr(m, "message_id", None) or "") in self._ja_gravados
        ]
        if not novas:
            return
        self._ja_gravados.update(
            i for i in (getattr(m, "message_id", None) for m in novas) if i
        )
        novas = _colapsar_reconstrucoes_duplicadas(novas)
        payload = [m.to_dict() for m in novas]
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
