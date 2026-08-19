"""A rota de documento reautoriza — sempre, e com o MESMO trim da recuperação.

POR QUE ISTO EXISTE. Esta é a primeira rota do produto que devolve o conteúdo INTEGRAL de um
documento com controle de acesso por documento. Se ela não reautorizar, vira o caminho que
contorna a RULE #6: bastaria adivinhar um nome de arquivo.

O QUE ELE GUARDA, e por que cada um:
  · nome inválido é recusado ANTES de qualquer I/O — `..%2f` não pode virar caminho
  · zero resultados no trim ⇒ PermissionError, nunca "não achei" (fail-closed)
  · o domínio com `document_access="acl"` manda o header de identidade e roda o trim; o
    `"session"` não roda o trim de jeito nenhum (não há `search_index` garantido nesses
    domínios — ex.: helpdesk — e não há DADO de ACL com que decidir; sessão válida, já exigida
    pela rota, é a regra inteira). A decisão é DECLARADA nesse campo, nunca derivada da
    truthiness de `acl_group_map` (IMPORTANT 1) — testado explicitamente abaixo.
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

    # `document_access` é o campo DECLARADO que decide (IMPORTANT 1) — não a truthiness de
    # `acl_group_map`, que fica aqui só porque outros pontos do domínio real também o carregam.
    com_acl = SimpleNamespace(
        id="selfwiki", search_index="selfwiki-docbundles-ks-index",
        search_endpoint="https://srch.example.net", corpus_container="selfwiki-corpus",
        acl_group_map={"app-users": "grupo-1"}, document_access="acl",
    )
    sem_acl = SimpleNamespace(
        id="helpdesk", search_index=None,  # helpdesk não seta search_index (I1) — de propósito
        search_endpoint="https://srch.example.net", corpus_container="corpus",
        acl_group_map=None, document_access="session",
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

    # ── a decisão é DECLARADA (document_access), não DERIVADA (acl_group_map) (IMPORTANT 1) ─
    # Prova direta de que a truthiness de `acl_group_map` não decide mais nada: um domínio com
    # `acl_group_map` PREENCHIDO mas `document_access="session"` (o cenário do achado — config
    # ausente/errada não pode rebaixar, e o inverso também não pode acontecer por acidente) NÃO
    # chama o trim.
    session_com_map_preenchido = SimpleNamespace(
        id="selfwiki", search_index="selfwiki-docbundles-ks-index",
        search_endpoint="https://srch.example.net", corpus_container="selfwiki-corpus",
        acl_group_map={"app-users": "grupo-1"},  # preenchido — e mesmo assim NÃO decide mais
        document_access="session",
    )
    chamadas.clear()
    try:
        asyncio.run(document.authorized_document(session_com_map_preenchido, "runbook-2.md", object()))
        check("document_access='session' não chama o trim mesmo com acl_group_map preenchido", True)
    except Exception as exc:
        check(
            f"document_access='session' não chama o trim mesmo com acl_group_map preenchido "
            f"(veio {type(exc).__name__}: {exc})",
            False,
        )
    check("document_access='session' NUNCA chama _contar_autorizado", chamadas == [])

    # E o inverso: `document_access="acl"` chama o trim mesmo com `acl_group_map` vazio — é
    # exatamente o cenário do achado (config de tenant ausente em runtime não pode rebaixar).
    acl_com_map_vazio = SimpleNamespace(
        id="selfwiki", search_index="selfwiki-docbundles-ks-index",
        search_endpoint="https://srch.example.net", corpus_container="selfwiki-corpus",
        acl_group_map={},  # vazio — e mesmo assim decide chamar o trim
        document_access="acl",
    )
    chamadas.clear()
    try:
        asyncio.run(document.authorized_document(acl_com_map_vazio, "runbook-3.md", object()))
        check("document_access='acl' chama o trim mesmo com acl_group_map vazio", False)
    except PermissionError:
        check("document_access='acl' chama o trim mesmo com acl_group_map vazio", True)
    except Exception as exc:
        check(
            f"document_access='acl' chama o trim mesmo com acl_group_map vazio "
            f"(veio {type(exc).__name__}: {exc})",
            False,
        )
    check("document_access='acl' chegou a chamar _contar_autorizado", chamadas != [])

    # ── domínio COM acl, auth ligada, sem token de usuário ⇒ PermissionError (I3) ───
    # Fail-closed: nunca roda o trim com a identidade da aplicação. `settings` é o singleton
    # de `app.shared.settings` — forçamos `auth_enabled` via os dois campos que a property
    # calcula, e restauramos no finally para não vazar para o resto do processo.
    #
    # O mock devolve 5 (não 0) neste cenário DE PROPÓSITO: com 0, o `PermissionError` esperado
    # viria do "zero resultados no trim" mesmo se a guarda de fail-closed (que barra ANTES de
    # chamar o trim) fosse removida — o check passaria por coincidência. Com 5, só a guarda
    # explica o `PermissionError`; se alguém a remover, o trim rodaria "como a aplicação",
    # devolveria 5 (>0) e o check pega a regressão.
    async def busca_falsa_5(*, endpoint, index, filtro, token, user_token):
        chamadas.append({"index": index, "filtro": filtro, "user_token": user_token})
        return 5

    chamadas.clear()
    tid_original = document.settings.entra_tenant_id
    cid_original = document.settings.entra_api_client_id
    document.settings.entra_tenant_id = "tid-de-teste"
    document.settings.entra_api_client_id = "cid-de-teste"
    document._user_search_token = token_nenhum
    document._contar_autorizado = busca_falsa_5
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
