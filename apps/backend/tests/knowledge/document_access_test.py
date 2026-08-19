"""A rota de documento reautoriza — sempre, e com o MESMO trim da recuperação.

POR QUE ISTO EXISTE. Esta é a primeira rota do produto que devolve o conteúdo INTEGRAL de um
documento com controle de acesso por documento. Se ela não reautorizar, vira o caminho que
contorna a RULE #6: bastaria adivinhar um nome de arquivo.

O QUE ELE GUARDA, e por que cada um:
  · nome inválido é recusado ANTES de qualquer I/O — `..%2f` não pode virar caminho
  · zero resultados no trim ⇒ PermissionError, nunca "não achei" (fail-closed)
  · o domínio COM acl_group_map manda o header de identidade; o SEM, não
  · a URL é CONSTRUÍDA do container configurado, nunca aceita do chamador (SSRF)
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from app.modules.knowledge.internal import document


def main() -> int:
    print("a rota de documento reautoriza por usuário")
    falhas: list[str] = []

    def check(nome: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FALHA'} {nome}")
        if not ok:
            falhas.append(nome)

    com_acl = SimpleNamespace(
        id="selfwiki", search_index="selfwiki-docbundles-ks-index",
        search_endpoint="https://srch.example.net", corpus_container="selfwiki-corpus",
        acl_group_map={"app-users": "grupo-1"},
    )
    sem_acl = SimpleNamespace(
        id="helpdesk", search_index="helpdesk-runbooks-ks-index",
        search_endpoint="https://srch.example.net", corpus_container="corpus",
        acl_group_map=None,
    )

    # ── nome inválido é recusado antes de qualquer I/O ──────────────────────────────
    for ruim in ("../secreto.md", "a/b.md", "", "x" * 300, "arquivo com espaço.md"):
        try:
            asyncio.run(document.authorized_document(com_acl, ruim, None))
            check(f"recusa nome inválido {ruim[:18]!r}", False)
        except ValueError:
            check(f"recusa nome inválido {ruim[:18]!r}", True)
        except Exception as exc:
            check(f"recusa nome inválido {ruim[:18]!r} (veio {type(exc).__name__})", False)

    # ── o trim manda: zero resultados ⇒ PermissionError ─────────────────────────────
    chamadas: list[dict] = []

    async def busca_falsa(*, endpoint, index, filtro, token, user_token):
        chamadas.append({"index": index, "filtro": filtro, "user_token": user_token})
        return 0  # ninguém autorizado

    async def token_falso(user):
        return "token-do-usuario"

    document._contar_autorizado = busca_falsa
    document._user_search_token = token_falso
    document._token_app = lambda: asyncio.sleep(0, result="token-app")

    try:
        asyncio.run(document.authorized_document(com_acl, "page-11.md", object()))
        check("zero no trim levanta PermissionError", False)
    except PermissionError:
        check("zero no trim levanta PermissionError", True)
    except Exception as exc:
        check(f"zero no trim levanta PermissionError (veio {type(exc).__name__}: {exc})", False)

    ultima = chamadas[-1] if chamadas else {}
    check("o filtro é por blob_url construída, não por nome cru",
          "blob_url eq '" in str(ultima.get("filtro", "")))
    check("a URL construída aponta para o container configurado",
          "/selfwiki-corpus/page-11.md'" in str(ultima.get("filtro", "")))
    check("domínio COM acl manda a identidade do usuário",
          ultima.get("user_token") == "token-do-usuario")

    # ── domínio sem ACL não manda identidade ────────────────────────────────────────
    chamadas.clear()
    try:
        asyncio.run(document.authorized_document(sem_acl, "runbook-1.md", object()))
    except Exception:
        pass
    ultima = chamadas[-1] if chamadas else {}
    check("domínio SEM acl não manda identidade", ultima.get("user_token") is None)

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
