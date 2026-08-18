"""O mesmo `record_usage`, pelo ponto canônico do LangChain.

POR QUE UM SEGUNDO PONTO DE ENTRADA, E NÃO UMA SEGUNDA CONTABILIDADE. Os domínios `oncall` e
`deepcall` rodam em LangGraph e constroem `AzureChatOpenAI` — não passam pela fábrica de cliente do
agent-framework, então o `ChatMiddleware` que mede todo o resto não os alcança. Eles ficavam
INTEIRAMENTE fora da medição: gravavam chamado e decisão de HITL (a parte cara de acertar) e não
gravavam nem conversa nem token (a parte barata).

A tentação seria dar a eles um contador próprio. Isso criaria dois números para a mesma pergunta, e
números que se respondem em dois lugares divergem sem dar erro — foi assim que a tabela de preço do
`wiki_builder` se separou da do `cost.py`. Aqui o callback chama o MESMO `record_usage`: uma
contabilidade, dois pontos de entrada.

O PONTO É CANÔNICO, não adaptado. `BaseCallbackHandler.on_llm_end` recebe um `LLMResult` cujo
`llm_output` traz o `token_usage` — é a superfície de observabilidade do próprio LangChain, do
mesmo jeito que `ChatMiddleware` é a do agent-framework. A ADR-020 diz exatamente isto: cada
framework se usa do jeito mais canônico dele, e o que compartilhamos é o destino, não o mecanismo.

O QUE ELE NÃO FAZ: gravar o turno da conversa. O `on_llm_end` vê a resposta do MODELO, que num
grafo com HITL inclui passos internos que ninguém quer reler. O turno visível é do grafo, não da
chamada — e vai por outro caminho quando houver.
"""

from __future__ import annotations

import logging
from typing import Any

logger = logging.getLogger(__name__)


def _tokens(resultado: Any) -> tuple[int, int]:
    """`(entrada, saída)` de um `LLMResult`. Zero quando o provedor não devolve uso.

    Aceita as duas grafias porque elas coexistem: `prompt_tokens`/`completion_tokens` é o formato
    da OpenAI, `input_tokens`/`output_tokens` é o das convenções GenAI. Ler só uma devolveria zero
    em silêncio para metade dos provedores.
    """
    saida_llm = getattr(resultado, "llm_output", None) or {}
    uso = saida_llm.get("token_usage") or saida_llm.get("usage") or {}
    if not isinstance(uso, dict):
        return 0, 0
    entrada = int(uso.get("prompt_tokens") or uso.get("input_tokens") or 0)
    saida = int(uso.get("completion_tokens") or uso.get("output_tokens") or 0)
    return entrada, saida


def usage_callback():
    """O handler para passar em `AzureChatOpenAI(callbacks=[...])`.

    Devolve uma instância nova a cada chamada: o handler é sem estado, mas o modelo é construído
    por requisição e compartilhar instância entre requisições concorrentes é o tipo de coisa que
    funciona até não funcionar.
    """
    from langchain_core.callbacks import BaseCallbackHandler

    class _GravadorDeUso(BaseCallbackHandler):
        def on_llm_end(self, response: Any, **kwargs: Any) -> None:
            from app.modules.conversations.internal.listing import record_usage
            from app.modules.conversations.internal.recorder import current_conversation
            from app.modules.conversations.internal.store import conversation_user

            atual = current_conversation()
            if atual is None:
                return
            entrada, saida = _tokens(response)
            if entrada or saida:
                # `record_usage` já é silencioso em falha: contabilidade não derruba conversa.
                record_usage(conversation_user(), atual[0], atual[1], entrada, saida)

    return _GravadorDeUso()
