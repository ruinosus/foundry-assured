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

from agent_framework import AgentMiddleware, ChatMiddleware
from fastapi import Request

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


def bind_dependency(agent: str = "", *, path_param: str = ""):
    """Dependência do FastAPI que amarra `(agente, thread)` a esta requisição.

    MORA AQUI, e não no registry, porque a amarração é do módulo de conversas — e porque ela
    precisa valer para DUAS famílias de rota que não compartilham código: os domínios do registry
    (`mount_domains`) e as rotas hosted (`app/modules/hosted/api.py`). Enquanto ela existia só no
    registry, as rotas hosted ficavam de fora — inclusive `/foundry-agent/{name}`, que é o agente
    que o USUÁRIO cria, a superfície menos instrumentada de todas.

    `agent` fixo serve o domínio; `path_param` serve a rota genérica, onde a identidade só se
    conhece por requisição (`/foundry-agent/{name}`). Sem isso, ou a rota genérica ficaria sem
    amarração, ou todas as conversas de agentes diferentes cairiam sob a mesma chave.

    A ANOTAÇÃO `request: Request` NÃO É DECORAÇÃO. Sem ela o FastAPI trata o parâmetro como query
    param obrigatório e devolve 422 antes de chamar a função — a amarração nunca roda, e nas rotas
    reais o erro fica MASCARADO porque a autenticação responde 401 primeiro. Foi assim que ela
    passou despercebida no commit anterior.

    `request.json()` guarda o corpo em cache no próprio objeto (`Request._body`), então lê-lo aqui
    não consome o stream que o adapter vai ler depois. Corpo que não é JSON — ou sem thread —
    simplesmente não amarra, e o gravador vira no-op.
    """

    async def _amarrar(request: Request) -> None:
        nome = agent
        if path_param:
            nome = str(request.path_params.get(path_param, "") or "") or agent
        if not nome:
            return
        try:
            corpo = await request.json()
        except Exception:  # noqa: BLE001 — corpo não-JSON não amarra, e não derruba a requisição
            return
        if isinstance(corpo, dict):
            thread = corpo.get("threadId") or corpo.get("thread_id") or ""
            bind_conversation(nome, str(thread))

    return _amarrar


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


class AgentUsageRecorder(AgentMiddleware):
    """O mesmo `record_usage`, na camada de AGENTE.

    POR QUE UMA TERCEIRA PORTA. `FoundryAgent` — a classe que fala com o agente PUBLICADO — aceita
    `middleware`, mas a docstring do próprio pacote diz "agent-level middleware". Um `ChatMiddleware`
    passado ali é **silenciosamente ignorado**: medido, ele não roda, e o efeito em produção foi
    token zerado numa conversa que gravou tudo o mais. O `FoundryAgent` constrói o cliente por
    dentro, então não há onde pendurar o middleware de chat.

    A conta continua sendo UMA. `ChatMiddleware` para quem passa pela fábrica de cliente,
    `on_llm_end` para o LangChain, e este para quem é `FoundryAgent` — três portas, um
    `record_usage`. Dois contadores para a mesma pergunta divergem sem dar erro; três portas para o
    mesmo contador, não.

    Só entra onde o de chat NÃO alcança. Pendurar os dois no mesmo caminho contaria cada token duas
    vezes — e um número dobrado num painel de custo é pior que um ausente, porque parece medido.
    """

    async def process(self, context, call_next):  # type: ignore[override]
        context.stream_result_hooks.append(self._registrar)
        await call_next()
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

            record_usage(conversation_user(), atual[0], atual[1], entrada, saida)
        return response


def agent_usage_recorder() -> AgentUsageRecorder:
    """O gravador para agentes que não passam pela fábrica de cliente (ex.: `FoundryAgent`)."""
    return AgentUsageRecorder()


def usage_recorder() -> UsageRecorder:
    """O gravador, para a fábrica de cliente anexar. Uma instância por cliente é suficiente."""
    return UsageRecorder()
