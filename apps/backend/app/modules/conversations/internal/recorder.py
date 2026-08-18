"""UM lugar grava o uso de TODOS os agentes — não cada agente gravando o seu.

POR QUE ISTO EXISTE. Antes daqui, `record_usage` era chamado de um único arquivo
(`grounded/internal/grounded.py`), e o resultado apareceu no painel de ROI: `selfwiki` com 656
tokens e todos os outros domínios com zero. A causa não era esquecimento — era estrutural. Cada
módulo constrói o SEU `FoundryChatClient` (eram cinco construções: helpdesk, grounded, platform,
builder, wiki_builder), então cada agente também decidia por conta se gravava algo. Instrumentar
os que faltavam, um por um, garantiria que o próximo agente nascesse fora da contabilidade — que
é como este bug nasceu.

A COSTURA É `ChatMiddleware`, do próprio framework. Ele intercepta a chamada ao modelo, que é
exatamente onde o token existe, e vale para qualquer agente construído pelo framework. Verificado
contra o pacote instalado: `ChatContext.stream_result_hooks` é uma LISTA de hooks aplicados à
resposta FINALIZADA — em streaming o uso só existe no fim, então é ali que se lê, e não em
`context.result`, que durante o stream ainda é um `ResponseStream`. `ChatResponse.usage_details`
carrega os contadores.

O QUE ESTE HOOK NÃO FAZ: contar referências de conhecimento. Token é universal — toda chamada de
modelo tem. Referência existe só onde houve recuperação de fonte, e a resposta do chat não a
carrega: quem tem as fontes em mãos é o caminho que as buscou. Em `platform` (tool-driven) e
`builder` (sem base) o zero é REAL, não ausente. Fingir que um hook só pega as duas coisas
produziria uma contagem de referências silenciosamente errada, que é pior que uma ausente.
"""

from __future__ import annotations

import contextvars
import logging
from typing import Any

from agent_framework import ChatMiddleware

logger = logging.getLogger(__name__)

#: A conversa DESTA requisição: `(agente, id da conversa)`.
#:
#: Existe porque os dois lados da medição sabem metades diferentes. O middleware vê o token e não
#: sabe de que conversa é; a requisição sabe a conversa e não vê o token. Mesmo padrão que
#: `shared/auth._current_user` e `tenancy._current_tenant` já usam neste backend — não é mecanismo
#: novo, é o mecanismo da casa.
_current: contextvars.ContextVar[tuple[str, str] | None] = contextvars.ContextVar(
    "current_conversation", default=None
)


def bind_conversation(agent: str, conversation_id: str) -> None:
    """Amarra a conversa desta requisição. Chamado UMA vez, na dependência de todo domínio."""
    if agent and conversation_id:
        _current.set((agent, conversation_id))


def current_conversation() -> tuple[str, str] | None:
    """`(agente, conversa)` desta requisição, ou None fora de uma."""
    return _current.get()


def _tokens(uso: Any) -> tuple[int, int]:
    """`(entrada, saída)` de um `UsageDetails`, que é um mapa.

    Lido por `.get`, não por atributo: `UsageDetails` expõe interface de dicionário (verificado —
    `keys`/`items`/`get`), e ler por atributo devolveria zero em silêncio.
    """
    if not uso:
        return 0, 0
    try:
        entrada = int(uso.get("input_token_count") or uso.get("input_tokens") or 0)
        saida = int(uso.get("output_token_count") or uso.get("output_tokens") or 0)
    except Exception:  # noqa: BLE001 — formato inesperado não derruba a conversa
        return 0, 0
    return entrada, saida


class UsageRecorder(ChatMiddleware):
    """Soma os tokens de cada chamada de modelo na conversa desta requisição.

    Silencioso e sem efeito quando não há conversa amarrada — é o caso do `wiki_builder`, que roda
    por CLI e não é conversa de ninguém. Assim a fábrica de cliente pode ser uniforme: todo cliente
    ganha o gravador, e o gravador decide sozinho que não há o que gravar.
    """

    async def process(self, context, call_next):  # type: ignore[override]
        context.stream_result_hooks.append(self._registrar)
        await call_next()
        # Caminho não-streaming: aqui `context.result` já é a resposta pronta. Em streaming ela é
        # um `ResponseStream` e o hook acima é quem responde — por isso os dois existem, e por isso
        # `_registrar` é idempotente por natureza (soma zero quando não há uso).
        resultado = getattr(context, "result", None)
        if resultado is not None and hasattr(resultado, "usage_details"):
            self._registrar(resultado)

    def _registrar(self, response):
        atual = current_conversation()
        if atual is None:
            return response
        entrada, saida = _tokens(getattr(response, "usage_details", None))
        if entrada or saida:
            from app.modules.conversations.internal.listing import record_usage
            from app.modules.conversations.internal.store import conversation_user

            # `record_usage` já é silencioso em falha: contabilidade não derruba chat.
            record_usage(conversation_user(), atual[0], atual[1], entrada, saida)
        return response


def usage_recorder() -> UsageRecorder:
    """O gravador, para a fábrica de cliente anexar. Uma instância por cliente é suficiente."""
    return UsageRecorder()
