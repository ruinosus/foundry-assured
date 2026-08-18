"""Os domínios de grafo gravam o TURNO, e o gravam uma vez só.

POR QUE ESTE TESTE EXISTE. `oncall` e `deepcall` eram as duas últimas superfícies que não salvavam
a conversa. Elas rodam em LangGraph e não passam pela fábrica de cliente do agent-framework, então
nem o middleware que mede token nem o `HistoryProvider` que grava transcrição as alcançam.

O ponto de gravação NÃO é o mesmo do token, e é isso que o teste fixa. São dois níveis:

    on_llm_end     → a resposta do MODELO. É onde o token existe. Num grafo com HITL isso inclui
                     passos internos que ninguém quer reler, então gravar o TURNO aqui encheria a
                     transcrição de ruído.
    on_chain_end   → o estado final do GRAFO, com a transcrição. É onde o turno existe. Gravar o
                     TOKEN aqui perderia as chamadas intermediárias.

O FILTRO DE RAIZ É O QUE IMPEDE DUPLICATA. `on_chain_end` dispara para cada sub-cadeia; medido,
numa execução simples são duas chamadas e só uma tem `parent_run_id is None`. Sem o filtro o mesmo
turno entraria mais de uma vez por execução — e uma transcrição com a resposta repetida é pior que
uma ausente, porque parece correta.

O modelo é o `FakeMessagesListChatModel` do próprio LangChain, e o grafo é um `create_agent` real:
o que se prova é o comportamento do CALLBACK dentro de um grafo de verdade, sem rede.
"""

from __future__ import annotations

import sys


def main() -> int:
    from langchain.agents import create_agent
    from langchain_core.language_models.fake_chat_models import (
        FakeMessagesListChatModel,
    )
    from langchain_core.messages import AIMessage

    from app.modules.conversations.internal import listing
    from app.modules.conversations.internal import store as store_mod
    from app.modules.conversations.public import bind_conversation, usage_callback

    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    memoria = store_mod.InMemoryConversationStore()
    store_original, user_original = listing.store, store_mod.conversation_user
    listing.store = lambda: memoria
    store_mod.conversation_user = lambda: "u-1"
    try:
        bind_conversation("oncall", "thread-1")
        grafo = create_agent(
            model=FakeMessagesListChatModel(responses=[AIMessage(content="resposta do grafo")]),
            tools=[],
            system_prompt="x",
        )
        grafo.invoke(
            {"messages": [("user", "pergunta ao grafo")]},
            config={"callbacks": [usage_callback()]},
        )

        linhas = memoria.read("u-1", "oncall", "thread-1")
        textos = " ".join(str(linha) for linha in linhas)
        check(f"o turno do grafo foi gravado ({len(linhas)} mensagens)", len(linhas) == 2)
        check("a PERGUNTA está na transcrição", "pergunta ao grafo" in textos)
        check("a RESPOSTA está na transcrição", "resposta do grafo" in textos)
        check(
            "gravado UMA vez — o filtro de raiz impede a duplicata por sub-cadeia",
            textos.count("resposta do grafo") == 1,
        )

        # Sem conversa amarrada não há onde gravar, e inventar uma chave misturaria o histórico de
        # execuções diferentes. O callback é no-op, não erro.
        from app.modules.conversations.internal.recorder import _current

        _current.set(None)
        memoria2 = store_mod.InMemoryConversationStore()
        listing.store = lambda: memoria2
        grafo.invoke(
            {"messages": [("user", "sem amarração")]},
            config={"callbacks": [usage_callback()]},
        )
        check("sem conversa amarrada, o callback é no-op", not memoria2._linhas)
    finally:
        listing.store, store_mod.conversation_user = store_original, user_original

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ os domínios de grafo gravam o turno, uma vez, no nível certo.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
