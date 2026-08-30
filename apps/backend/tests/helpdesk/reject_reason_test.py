"""O payload da decisão: a recusa carrega o motivo, e nada malformado vira aprovação.

POR QUE ESTE TESTE EXISTE. `_read_answer` é o ponto onde uma decisão humana vira uma decisão do
sistema, e ele já tinha uma propriedade fail-closed guardada só por um comentário: *qualquer
payload não reconhecido é REJECT, nunca approve*. Ao acrescentar o motivo da recusa, essa função
passou a devolver três valores em vez de dois — exatamente o tipo de mudança em que uma tupla
desempacotada errado transforma um motivo em argumento, ou pior, um lixo em aprovação.

O que ele guarda:

1. `reject` carrega o `message` — sem isso, "recusar exige motivo" seria uma regra que só existe
   na tela, e o motivo morreria no caminho entre o clique e o backend;
2. o motivo é lido SÓ para `reject` — anexado a um `approve` seria um campo que ninguém lê
   depois, e num `edit` a correção já é a mensagem;
3. o motivo é limitado — ele atravessa para o output do workflow, e um payload de megabytes
   entraria inteiro na conversa;
4. **payload malformado continua virando REJECT** — a propriedade que já existia, agora com um
   teste. Um payload malformado nunca pode ser a razão de um chamado abrir (RULE #5).

    uv run python -m tests.helpdesk.reject_reason_test
"""

from __future__ import annotations

import sys

from app.modules.helpdesk.internal.escalation import MAX_MOTIVO, _read_answer


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    # --- 1 · a recusa carrega o motivo ---------------------------------------------------
    tipo, args, motivo = _read_answer({"type": "reject", "message": "o runbook exige verificação"})
    check("reject carrega o motivo", tipo == "reject" and motivo == "o runbook exige verificação")
    check("reject não inventa args", args == {})

    # --- 2 · o motivo é lido SÓ para reject ----------------------------------------------
    _, _, m_aprovado = _read_answer({"type": "approve", "message": "não deveria ser lido"})
    check("approve descarta o motivo", m_aprovado == "")
    _, a_editado, m_editado = _read_answer(
        {"type": "edit", "args": {"summary": "corrigido"}, "message": "idem"}
    )
    check("edit descarta o motivo (a correção já é a mensagem)", m_editado == "")
    check("…e preserva a correção", a_editado == {"summary": "corrigido"})

    # --- 3 · o motivo é limitado ----------------------------------------------------------
    _, _, longo = _read_answer({"type": "reject", "message": "x" * (MAX_MOTIVO + 500)})
    check(f"motivo é truncado em {MAX_MOTIVO}", len(longo) == MAX_MOTIVO)
    _, _, so_espaco = _read_answer({"type": "reject", "message": "   \n  "})
    check("motivo só de espaço vira vazio", so_espaco == "")

    # --- 4 · fail-closed: nada malformado vira aprovação ----------------------------------
    # A propriedade mais importante do arquivo, e a que não tinha teste. Cada entrada abaixo é
    # uma forma real de payload chegar torto: tipo desconhecido, tipo ausente, tipo em outro
    # idioma, lista no lugar de dict, nulo, string solta.
    malformados: list[object] = [
        {"type": "aprovar"},
        {"type": ""},
        {},
        {"type": "APPROVE!"},
        ["approve"],
        None,
        "approve",
        42,
        {"type": None},
    ]
    for payload in malformados:
        t, _, _ = _read_answer(payload)
        check(f"payload {payload!r} vira reject", t == "reject")

    # O booleano legado continua valendo — é o que a tela mandava antes da ADR-019.
    check("True continua sendo approve", _read_answer(True)[0] == "approve")
    check("False continua sendo reject", _read_answer(False)[0] == "reject")
    # `True` é instância de `int` em Python: se a ordem dos isinstance mudar, um `1` viraria
    # aprovação. Este check é o que trava essa regressão.
    check("o inteiro 1 NÃO é approve", _read_answer(1)[0] == "reject")

    # A maiúscula é normalizada de propósito (a tela pode mandar "Reject"), e isso não afrouxa
    # nada: o conjunto aceito continua sendo o mesmo três.
    check("o tipo é normalizado para minúsculas", _read_answer({"type": "Approve"})[0] == "approve")

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ a recusa leva o motivo, e nenhum payload torto abre chamado.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
