"""A resposta do FoundryAgent publicado não é gravada duas vezes.

O QUE FOI MEDIDO. Baixei o blob real de uma conversa do `selfwiki` gravada com
`GROUNDED_VIA_FRAMEWORK=true` (`59064647-…/selfwiki/bb82ca58-….jsonl`, conta
`stassuredf2pijerpyr3zi`) e cada um dos três turnos tinha o mesmo padrão: DUAS mensagens de
assistente onde deveria haver uma.

    [0] user      contents=[text]                                    "Como funciona…?"
    [1] assistant contents=[text_reasoning(vazio), text]  author_name="selfwiki"  message_id=None
    [2] assistant contents=[text]                          author_name=None       message_id=<real>

O `text` de [1] e [2] é BYTE A BYTE idêntico (conferido pelo tamanho e pelo prefixo, 6936/4874/2992
caracteres nos três turnos). Não são duas respostas — são duas RECONSTRUÇÕES da mesma resposta em
streaming: `AgentResponse.from_updates()` (acumulada localmente a partir dos updates) e
`stream.get_final_response()` (o objeto final do serviço). `HistoryProvider.after_run()` do
framework grava tudo que está em `response.messages` sem saber que as duas descrevem o mesmo
turno — por isso o `StoredHistoryProvider.save_messages` precisa colapsá-las antes de persistir.

POR QUE ISTO NÃO É O MESMO BUG JÁ CONSERTADO. O dedup existente (`_ja_gravados`) resolve o
reenvio da THREAD INTEIRA entre turnos — mensagens que JÁ estavam no store. Este bug é DENTRO do
mesmo `save_messages`, na MESMA chamada: as duas mensagens são novas, nenhuma das duas está em
`_ja_gravados` ainda, então aquele filtro não pega — e não deveria, é um problema diferente.

A PROVA POR MUTAÇÃO que valida este teste (não automatizada aqui, rodada manualmente ao consertar):
comentar a chamada a `_colapsar_reconstrucoes_duplicadas` em `provider.py` faz a verificação
"grava exatamente duas mensagens" falhar (viram três), e restaurar a chamada faz voltar a passar.
"""

from __future__ import annotations

import asyncio
import sys

USUARIO = "u-prova-dup"
CONVERSA = "thread-prova-dup"
AGENTE = "selfwiki"


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    from agent_framework import Message

    from app.modules.conversations.internal import provider as provider_mod
    from app.modules.conversations.internal import store as store_mod

    # ── unidade: `_colapsar_reconstrucoes_duplicadas` isolada ────────────────────────────
    texto = "## Resumo\nO mecanismo de assurance é baseado em testes automatizados."

    sem_id = Message(
        "assistant",
        [{"type": "text_reasoning", "text": ""}, {"type": "text", "text": texto}],
        author_name="selfwiki",
    )
    com_id = Message("assistant", [{"type": "text", "text": texto}], message_id="resp-real-1")
    pergunta = Message("user", [texto], message_id="user-1")

    colapsado = provider_mod._colapsar_reconstrucoes_duplicadas([pergunta, sem_id, com_id])
    check("a reconstrução sem id é descartada quando o texto bate", len(colapsado) == 2)
    check("sobra a mensagem COM message_id (a única reaproveitável por _ja_gravados)",
          any(getattr(m, "message_id", None) == "resp-real-1" for m in colapsado))
    check("a pergunta do usuário não é afetada", pergunta in colapsado)

    # Duas respostas DE VERDADE (textos diferentes) não podem colapsar.
    r1 = Message("assistant", [{"type": "text", "text": "resposta A"}], message_id="id-a")
    r2 = Message("assistant", [{"type": "text", "text": "resposta B"}])
    check(
        "textos diferentes não colapsam (não é o mesmo bug)",
        len(provider_mod._colapsar_reconstrucoes_duplicadas([r1, r2])) == 2,
    )

    # Coincidência de texto VAZIO não deve apagar uma resposta real por engano.
    v1 = Message("assistant", [{"type": "text", "text": ""}])
    v2 = Message("assistant", [{"type": "text", "text": ""}], message_id="id-vazio")
    check(
        "coincidência de texto vazio não colapsa",
        len(provider_mod._colapsar_reconstrucoes_duplicadas([v1, v2])) == 2,
    )

    # ── ponta a ponta: `StoredHistoryProvider.save_messages` grava só UMA vez ────────────
    #
    # `provider.py` faz `from ...store import store` no próprio módulo — trocar o símbolo em
    # `store_mod` não o alcança (já aconteceu neste repo: um teste anterior "provou" que a
    # conversa não era gravada, e o problema era só o remendo errado). Troca-se em `provider_mod`.
    memoria = store_mod.InMemoryConversationStore()
    original = provider_mod.store
    provider_mod.store = lambda: memoria
    try:
        prov = provider_mod.StoredHistoryProvider(USUARIO, AGENTE, CONVERSA)

        async def _turno() -> None:
            await prov.get_messages(CONVERSA)
            # A FORMA REAL medida no blob: a reconstrução sem id chega ANTES da com id em
            # `response.messages` (é a ordem observada — reasoning some primeiro, o texto final
            # do serviço depois) — mas o colapso não deve depender de ordem.
            entrada = Message("user", ["Como funciona o mecanismo de assurance?"], message_id="u-1")
            sem_id_turno = Message(
                "assistant",
                [{"type": "text_reasoning", "text": ""}, {"type": "text", "text": texto}],
                author_name="selfwiki",
            )
            com_id_turno = Message("assistant", [{"type": "text", "text": texto}], message_id="a-1")
            await prov.save_messages(CONVERSA, [entrada, sem_id_turno, com_id_turno])

        asyncio.run(_turno())

        gravadas = memoria.read(USUARIO, AGENTE, CONVERSA)
        check(
            f"o turno grava EXATAMENTE duas mensagens, não três ({len(gravadas)})",
            len(gravadas) == 2,
        )
        respostas = [m for m in gravadas if m.get("role") == "assistant"]
        check("só UMA resposta de assistente sobrevive", len(respostas) == 1)
        if respostas:
            check(
                "a que sobra é a que tem message_id (a reaproveitável pelo dedup entre turnos)",
                respostas[0].get("message_id") == "a-1",
            )
    finally:
        provider_mod.store = original

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam — a resposta está sendo duplicada.")
        return 1
    print("\n✅ a resposta do FoundryAgent publicado é gravada uma única vez por turno.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
