"""A conversa acumula, é isolada por pessoa, e o caminho não aceita travessia.

    uv run python -m tests.conversations.conversation_store_test

POR QUE ESTE TESTE EXISTE, e não é cerimônia: a primeira versão do store gravava com
`create_append_blob()` sem condição, que **sobrescreve** um blob existente em vez de falhar. Cada
turno zerava a conversa e a leitura devolvia só o último — sem exceção, sem log, sem sintoma na
tela além de um assistente que "esquece". Um teste pegou em trinta segundos.

Roda offline, sobre o `InMemoryConversationStore`, porque o que está sendo travado é o CONTRATO
(acumula, isola, recusa travessia), não o SDK do Azure. O comportamento condicional do append blob
foi verificado contra o serviço real e está documentado em `store.py`; aqui trava-se o que um
teste offline consegue provar todo push.
"""

from __future__ import annotations

import sys

from app.modules.conversations.internal.store import (
    InMemoryConversationStore,
    InvalidKey,
    _titulo,
)

failures: list[str] = []


def check(nome: str, condicao: bool) -> None:
    marca = "✓" if condicao else "✗"
    print(f"  {marca} {nome}")
    if not condicao:
        failures.append(nome)


def main() -> int:
    print("conversas — contrato do store\n")
    s = InMemoryConversationStore()

    # ACUMULA. O bug original vivia exatamente aqui.
    s.append("u1", "helpdesk", "c1", [{"role": "user", "text": "primeira"}])
    s.append("u1", "helpdesk", "c1", [{"role": "assistant", "text": "resposta"}])
    s.append("u1", "helpdesk", "c1", [{"role": "user", "text": "segunda"}])
    msgs = s.read("u1", "helpdesk", "c1")
    check("três apêndices produzem três mensagens", len(msgs) == 3)
    check("a ordem é a de gravação", [m["text"] for m in msgs] == ["primeira", "resposta", "segunda"])

    # ISOLA. Duas pessoas com o mesmo id de conversa não se enxergam.
    s.append("u2", "helpdesk", "c1", [{"role": "user", "text": "de outra pessoa"}])
    check("outro usuário não lê a conversa do primeiro", len(s.read("u1", "helpdesk", "c1")) == 3)
    check("cada um lê a sua", s.read("u2", "helpdesk", "c1")[0]["text"] == "de outra pessoa")
    check("a lista de u1 não mostra a conversa de u2", len(s.list("u1")) == 1)

    # SEPARA POR AGENTE. O filtro da tela depende disto.
    s.append("u1", "cockpit", "c9", [{"role": "user", "text": "outro domínio"}])
    check("sem filtro, vêm as duas", len(s.list("u1")) == 2)
    check("com filtro, vem uma", len(s.list("u1", "helpdesk")) == 1)

    # TÍTULO. É a primeira fala do USUÁRIO, não a do assistente — a lista precisa ser
    # reconhecível, e "Claro, posso ajudar" não identifica conversa nenhuma.
    check("título é a primeira fala do usuário", s.list("u1", "helpdesk")[0].title == "primeira")
    check(
        "título ignora o assistente",
        _titulo([{"role": "assistant", "text": "Claro!"}, {"role": "user", "text": "a pergunta"}])
        == "a pergunta",
    )
    check("título ausente não quebra", _titulo([{"role": "assistant", "text": "só isso"}]) == "")

    # TRAVESSIA. O id vira segmento de caminho; um `..` colocaria a conversa na pasta de outro.
    for ruim in ("../outro", "a/b", "", "x" * 200):
        try:
            s.read(ruim, "helpdesk", "c1")
            check(f"recusa segmento inválido {ruim[:12]!r}", False)
        except InvalidKey:
            check(f"recusa segmento inválido {ruim[:12]!r}", True)

    # VAZIO. Ler conversa inexistente é lista vazia, não explosão.
    check("conversa inexistente devolve vazio", s.read("u1", "helpdesk", "nao-existe") == [])

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ a conversa acumula, isola por pessoa e por agente, e recusa travessia de caminho.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
