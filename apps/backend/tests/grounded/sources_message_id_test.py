"""O evento `sources` diz A QUAL RESPOSTA ele pertence.

POR QUE ISTO EXISTE. O painel de evidência guardava só a última resposta, e a causa era
esta: o evento não carregava o id da mensagem, então a tela recebia uma lista solta e não
tinha onde arquivá-la. O `message_id` estava na mesma função, duas linhas acima do `yield`.

O `None` do caminho de workflow é DELIBERADO, não lacuna: ali o evento sai entre o retrieve
e o resolve, antes de a resposta existir. Quem consome liga o `None` à próxima mensagem que
começa — e essa ordem é o que este teste guarda.
"""

from __future__ import annotations

import pathlib
import re
import sys

import app as _app

RAIZ = pathlib.Path(_app.__file__).resolve().parent.parent
GROUNDED = RAIZ / "app" / "modules" / "grounded" / "internal" / "grounded.py"
EXECUTOR = RAIZ / "app" / "modules" / "grounded" / "internal" / "sources_executor.py"

falhas: list[str] = []


def check(nome: str, ok: bool) -> None:
    print(f"  {'ok  ' if ok else 'FALHA'} {nome}")
    if not ok:
        falhas.append(nome)


def main() -> int:
    print("evento `sources` carrega o id da resposta")

    g = GROUNDED.read_text(encoding="utf-8")
    # O emissor grounded tem o message_id em escopo — precisa usá-lo.
    check(
        "grounded.py emite sources com message_id",
        bool(re.search(r'CustomEvent\(\s*name="sources"[^)]*message_id', g, re.S)),
    )
    check(
        "grounded.py emite sources com a chave citations",
        bool(re.search(r'CustomEvent\(\s*name="sources"[^)]*"citations"', g, re.S)),
    )

    e = EXECUTOR.read_text(encoding="utf-8")
    check(
        "sources_executor emite a mesma forma (dict com citations)",
        bool(re.search(r'WorkflowEvent\(\s*"sources"[^)]*"citations"', e, re.S)),
    )
    check(
        "sources_executor manda message_id None e diz por quê",
        '"message_id": None' in e and "resolve" in e,
    )

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
