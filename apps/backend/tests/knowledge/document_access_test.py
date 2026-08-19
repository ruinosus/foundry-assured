"""A rota de documento reautoriza — sempre, e com o MESMO trim da recuperação.

POR QUE ISTO EXISTE. Esta é a primeira rota do produto que devolve o conteúdo INTEGRAL de um
documento com controle de acesso por documento. Se ela não reautorizar, vira o caminho que
contorna a RULE #6: bastaria adivinhar um nome de arquivo.

O QUE ELE GUARDA, e por que cada um:
  · nome inválido é recusado ANTES de qualquer I/O — `..%2f` não pode virar caminho
  · zero resultados no trim ⇒ PermissionError, nunca "não achei" (fail-closed)
  · o domínio COM acl_group_map manda o header de identidade e roda o trim; o SEM não roda o
    trim de jeito nenhum (não há `search_index` garantido nesses domínios — ex.: helpdesk — e
    não há DADO de ACL com que decidir; sessão válida, já exigida pela rota, é a regra inteira)
  · com ACL e auth ligada, ausência de token de usuário é PermissionError (fail-closed: nunca
    roda o trim "como a aplicação")
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
        id="helpdesk", search_index=None,  # helpdesk não seta search_index (I1) — de propósito
        search_endpoint="https://srch.example.net", corpus_container="corpus",
        acl_group_map=None,
    )

    # ── nome inválido é recusado antes de qualquer I/O ──────────────────────────────
    for ruim in ("../secreto.md", "a/b.md", "", "x" * 300, "arquivo com espaço.md", "abc.md\n"):
        try:
            asyncio.run(document.authorized_document(com_acl, ruim, None))
            check(f"recusa nome inválido {ruim[:18]!r}", False)
        except document.NomeDocumentoInvalido:
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

    async def token_nenhum(user):
        return None

    async def blob_falso(url, name):
        return b"conteudo-fake"

    document._contar_autorizado = busca_falsa
    document._user_search_token = token_falso
    document._token_app = lambda: asyncio.sleep(0, result="token-app")
    document._baixar_blob = blob_falso

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

    # ── domínio sem ACL não roda o trim (I1) ────────────────────────────────────────
    # Antes deste conserto o teste só checava que `user_token` viajava vazio — mas o código
    # SEMPRE chamava `_contar_autorizado`, só variando o header. Para o domínio helpdesk (sem
    # `search_index`) isso montava `.../indexes/None/docs/search` e caía em 500. A garantia
    # certa não é "identidade vazia", é "o trim nem roda" — é isso que este teste verifica
    # agora, e é por isso que `sem_acl.search_index` é `None` acima: se o código chamasse o
    # trim mesmo assim, `busca_falsa` receberia `index=None` e o teste pegaria isso também.
    chamadas.clear()
    try:
        _url, conteudo = asyncio.run(document.authorized_document(sem_acl, "runbook-1.md", object()))
        check("domínio SEM acl autoriza sem chamar o trim", True)
        check("domínio SEM acl devolve o conteúdo do blob (mockado)", conteudo == "conteudo-fake")
    except Exception as exc:
        check(f"domínio SEM acl autoriza sem chamar o trim (veio {type(exc).__name__}: {exc})", False)
    check("domínio SEM acl NUNCA chama _contar_autorizado", chamadas == [])

    # ── domínio COM acl, auth ligada, sem token de usuário ⇒ PermissionError (I3) ───
    # Fail-closed: nunca roda o trim com a identidade da aplicação. `settings` é o singleton
    # de `app.shared.settings` — forçamos `auth_enabled` via os dois campos que a property
    # calcula, e restauramos no finally para não vazar para o resto do processo.
    chamadas.clear()
    tid_original = document.settings.entra_tenant_id
    cid_original = document.settings.entra_api_client_id
    document.settings.entra_tenant_id = "tid-de-teste"
    document.settings.entra_api_client_id = "cid-de-teste"
    document._user_search_token = token_nenhum
    try:
        assert document.settings.auth_enabled  # a premissa do teste
        try:
            asyncio.run(document.authorized_document(com_acl, "page-12.md", object()))
            check("ACL + auth ligada + sem token de usuário ⇒ PermissionError", False)
        except PermissionError:
            check("ACL + auth ligada + sem token de usuário ⇒ PermissionError", True)
        except Exception as exc:
            check(
                f"ACL + auth ligada + sem token de usuário ⇒ PermissionError "
                f"(veio {type(exc).__name__}: {exc})",
                False,
            )
        check("nunca chega a chamar o trim sem token de usuário", chamadas == [])
    finally:
        document.settings.entra_tenant_id = tid_original
        document.settings.entra_api_client_id = cid_original
        document._user_search_token = token_falso

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
