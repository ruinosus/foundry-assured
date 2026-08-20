"""Gate: o header de identidade do Search leva o token CRU, nunca com `Bearer `.

`x-ms-query-source-authorization` é a única coisa que faz o trim por documento acontecer — sem
ele a busca devolve zero (fail-closed), e com ele MAL FORMADO a Azure devolve 401:

    Invalid header 'x-ms-query-source-authorization': BearerReadAccessTokenFailed

O nome do erro é uma armadilha: soa como "a leitura do token bearer falhou", quando significa "li
a string 'Bearer …' COMO SE fosse o token". Quem lê o 401 procura problema de permissão, de
audiência, de papel RBAC — tudo menos o prefixo. Custou uma investigação inteira: escopos
diferentes, cinco api-versions, papéis do service principal, identidade do serviço no Graph.

O `Authorization` da MESMA requisição leva `Bearer <token>`, então os dois convivem lado a lado
com regras opostas — é por isso que este gate existe em vez de um comentário.

Medido contra o índice do selfwiki, nos dois sentidos: com prefixo → 401; sem → documentos
carimbados. Todo o código de produção já passava cru; o verificador do CI divergiu por ter
remontado a requisição em vez de reusar o caminho existente.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import app

RAIZ = Path(app.__file__).resolve().parent.parent.parent.parent
HEADER = "x-ms-query-source-authorization"
# `"x-ms-query-source-authorization": ... Bearer` na MESMA atribuição
SUSPEITO = re.compile(rf'["\']{HEADER}["\']\s*[:=]\s*[^\n,}}]*Bearer', re.IGNORECASE)

ALVOS = ("apps/backend/app", "apps/backend/eval", "apps/backend/tests", ".github/workflows", "scripts")


def main() -> int:
    achados = []
    for alvo in ALVOS:
        base = RAIZ / alvo
        if not base.exists():
            continue
        for f in base.rglob("*"):
            if f.suffix not in (".py", ".yml", ".yaml", ".sh") or not f.is_file():
                continue
            try:
                texto = f.read_text(encoding="utf-8")
            except (UnicodeDecodeError, OSError):
                continue
            if f.resolve() == Path(__file__).resolve():
                continue  # este arquivo CITA o padrão errado para explicá-lo
            for n, linha in enumerate(texto.splitlines(), 1):
                # Comentário que explica a armadilha não é a armadilha. Em Python, YAML e shell
                # o comentário começa com `#`; sem esta linha o gate reprovaria a própria
                # documentação que existe para impedir o erro.
                if linha.lstrip().startswith("#"):
                    continue
                if SUSPEITO.search(linha):
                    achados.append((f.relative_to(RAIZ), n, linha.strip()[:100]))

    for caminho, n, linha in achados:
        print(f"  ✗ {caminho}:{n}\n      {linha}")
    if achados:
        print(
            f"\n✖ {len(achados)} lugar(es) mandam `Bearer` em {HEADER}. A Azure responde 401 "
            "`BearerReadAccessTokenFailed` — o token vai CRU neste header (só o `Authorization` "
            "leva o prefixo).",
            file=sys.stderr,
        )
        return 1
    print(f"  ✓ nenhum `Bearer` em {HEADER} — o token vai cru, como a Azure exige")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
