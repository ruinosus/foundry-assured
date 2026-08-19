"""O framework REALMENTE chama o provider que anexamos — a conversa é gravada de fato.

POR QUE ESTE TESTE EXISTE, e o que ele conserta na nossa própria disciplina. A matriz de
instrumentação (`tests/architecture/instrumentation_matrix_test.py`) verifica que cada superfície
DECLARA o que grava, e o gate de costura verifica que os pontos de gravação existem. Nenhum dos
dois prova que a gravação ACONTECE — os dois olham o fio, não a corrente.

E a diferença apareceu na prática: depois de ligar a gravação em seis superfícies novas, o store
continha exatamente UMA conversa, do `selfwiki`, anterior a todo o trabalho. "Ligado" e "provado"
não são a mesma coisa, e um placar de cobertura que não distingue os dois é o mesmo tipo de número
bonito que o painel de ROI existe para não ser.

O QUE ELE PROVA, sem rede e sem credencial: que um `Agent` de verdade do agent-framework, com o
`StoredHistoryProvider` anexado por `context_providers` — que é exatamente como `PerRequestAgent` e
o workflow do helpdesk o anexam —, escreve a conversa no store ao rodar. O cliente de chat é falso
(`BaseChatClient` tem UM método abstrato), mas o agente, o provider e o store são os reais.

O QUE ELE NÃO PROVA: que a requisição HTTP chega até aqui com usuário e thread amarrados. Isso é
das dependências de rota, e tem gate próprio (`usage_seam_test` verifica que a amarração roda e
sobrevive ao StreamingResponse). Entre os dois, o caminho fica coberto ponta a ponta por
composição — mas cada metade é dita pelo que ela é.
"""

from __future__ import annotations

import asyncio
import sys

USUARIO = "u-prova"
CONVERSA = "thread-prova"
AGENTE = "agente-de-prova"


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    from agent_framework import Agent, BaseChatClient, ChatResponse, Message

    from app.modules.conversations.internal import provider as provider_mod
    from app.modules.conversations.internal import store as store_mod
    from app.modules.conversations.public import build_history_provider

    # Store em memória: o backend real é blob, e a troca é o ponto de extensão previsto. O que se
    # prova aqui é que ALGO chega ao store, não qual store.
    # Trocar o símbolo em `provider`, NÃO em `store`: o provider faz `from ...store import store`
    # no topo, então já tem a referência resolvida e trocar na origem não o alcança. Errei isto na
    # primeira versão deste teste e ele acusou "a conversa não é gravada" — um falso positivo que,
    # se eu tivesse acreditado, teria me feito reescrever código que funciona.
    memoria = store_mod.InMemoryConversationStore()
    original = provider_mod.store
    provider_mod.store = lambda: memoria

    class Cliente(BaseChatClient):
        """O mínimo que `Agent` precisa: `BaseChatClient` tem UM método abstrato.

        É dublê de propósito. O que se prova aqui é o comportamento do AGENTE e do PROVIDER; um
        cliente real só acrescentaria rede — e rede num gate offline vira teste que ninguém roda.
        """

        async def _inner_get_response(self, *, messages, stream, options, **kwargs):
            return ChatResponse(messages=[Message("assistant", ["resposta fixa"])])

    try:
        historico = build_history_provider(USUARIO, AGENTE, CONVERSA)
        check("o provider é construído quando há usuário", historico is not None)
        if historico is None:
            return 1

        agente = Agent(client=Cliente(), instructions="prova", context_providers=[historico])
        asyncio.run(agente.run("pergunta de prova"))

        gravadas = memoria.read(USUARIO, AGENTE, CONVERSA)
        check(
            f"o framework chamou o provider e a conversa foi gravada ({len(gravadas)} mensagens)",
            len(gravadas) > 0,
        )
        textos = " ".join(str(m) for m in gravadas)
        check("a PERGUNTA do usuário está na transcrição", "pergunta de prova" in textos)
        check("a RESPOSTA do agente está na transcrição", "resposta fixa" in textos)

        # Sem usuário não há onde guardar, e gravar sob um anônimo compartilhado misturaria o
        # histórico de pessoas diferentes — que é vazamento, não conveniência.
        check("sem usuário, nenhum provider é criado", build_history_provider("", AGENTE, CONVERSA) is None)
    finally:
        provider_mod.store = original

    # ── a thread reenviada NÃO é regravada ────────────────────────────────────────────────
    #
    # No caminho AG-UI o cliente reenvia a CONVERSA INTEIRA a cada turno, e o framework repassa
    # isso como `input_messages`. Com este store sendo append-only, cada turno regravava tudo.
    # Medido numa conversa REAL de três perguntas: DOZE mensagens onde deviam ser seis, com a
    # primeira pergunta aparecendo três vezes.
    #
    # E o estrago não era só tamanho: o histórico duplicado volta como contexto do agente, e quem
    # procura "a última pergunta do usuário" nele acha uma pergunta antiga — foi o que fez a
    # recuperação buscar documentos da pergunta errada, e a conversa responder só a primeira.
    from agent_framework import Message as _Msg

    from app.modules.conversations.internal import provider as pmod

    memoria2 = store_mod.InMemoryConversationStore()
    pmod.store = lambda: memoria2
    prov = pmod.StoredHistoryProvider("u-1", "dominio", "th-1")

    def _m(papel: str, texto: str, mid: str):
        return _Msg(papel, [texto], message_id=mid)

    async def _turno(entrada, resposta):
        await prov.get_messages("th-1")
        await prov.save_messages("th-1", [*entrada, resposta])

    q1, a1 = _m("user", "Q1", "m1"), _m("assistant", "A1", "m2")
    q2, a2 = _m("user", "Q2", "m3"), _m("assistant", "A2", "m4")
    q3, a3 = _m("user", "Q3", "m5"), _m("assistant", "A3", "m6")
    asyncio.run(_turno([q1], a1))
    asyncio.run(_turno([q1, a1, q2], a2))
    asyncio.run(_turno([q1, a1, q2, a2, q3], a3))
    gravadas2 = memoria2.read("u-1", "dominio", "th-1")
    check(
        f"três turnos com a thread reenviada gravam SEIS mensagens, não doze ({len(gravadas2)})",
        len(gravadas2) == 6,
    )
    textos2 = " ".join(str(m) for m in gravadas2)
    check("…e cada pergunta aparece UMA vez", textos2.count("Q1") == 1 and textos2.count("Q3") == 1)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam — a conversa NÃO está sendo gravada.")
        return 1
    print("\n✅ o agente do framework grava a conversa pelo provider anexado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
