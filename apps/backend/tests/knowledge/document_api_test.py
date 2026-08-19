"""`GET /source/{domain_id}/{name}` — o mapeamento de exceção pra status HTTP, exercitado DE
VERDADE (I5). O teste antigo de `authorized_document` nunca chegava perto de `api.py`; não
existia teste nenhum da rota. Chama o handler como função Python simples (sem TestClient/rede):
`read_source` é uma corrotina comum, e `Response()` do FastAPI funciona standalone.

O que importa aqui, e por quê:
  · `PermissionError` -> 403, `FileNotFoundError` -> 404 — a distinção importa (fail-closed
    autenticado vs. recurso ausente) e antes deste teste não tinha gate nenhum sobre isso.
  · `NomeDocumentoInvalido` -> 400, mas um `ValueError` QUALQUER (ex.: `json.JSONDecodeError`
    vindo de uma falha de infraestrutura do Search) NÃO vira 400 — prova o conserto do M2 no
    ponto onde ele é visível de fora (a rota).
  · domínio `kind == "tool"` -> 404, sem sequer chamar `authorized_document`.
  · sem `set_domain_lookup` a rota falha fechada (500), nunca abre passagem.
  · o gate de entitlement (I2) só roda no modo `shared` — fora dele, nem é chamado.
"""

from __future__ import annotations

import asyncio
import sys
from types import SimpleNamespace

from fastapi import HTTPException, Response

from app.modules.knowledge import api
from app.modules.knowledge.internal.document import NomeDocumentoInvalido


def main() -> int:
    print("GET /source/{domain_id}/{name} — mapeamento de exceção")
    falhas: list[str] = []

    def check(nome: str, ok: bool) -> None:
        print(f"  {'ok  ' if ok else 'FALHA'} {nome}")
        if not ok:
            falhas.append(nome)

    domain_ok = SimpleNamespace(kind="grounded", id="selfwiki")
    domain_tool = SimpleNamespace(kind="tool", id="platform")

    modo_original = api.settings.deployment_mode
    lookup_original = api._domain_lookup
    require_domain_original = api.require_domain
    authorized_document_original = api.authorized_document
    current_user_original = api.current_user

    def restaurar() -> None:
        api.settings.deployment_mode = modo_original
        api._domain_lookup = lookup_original
        api.require_domain = require_domain_original
        api.authorized_document = authorized_document_original
        api.current_user = current_user_original

    try:
        api.settings.deployment_mode = "self_hosted"
        api.current_user = lambda: SimpleNamespace(oid="user-1")

        # ── sem set_domain_lookup, a rota falha fechada ──────────────────────────────
        api._domain_lookup = None
        try:
            asyncio.run(api.read_source("selfwiki", "page.md", Response()))
            check("sem set_domain_lookup falha fechada (500)", False)
        except HTTPException as exc:
            check("sem set_domain_lookup falha fechada (500)", exc.status_code == 500)

        # ── domínio desconhecido -> 404 ───────────────────────────────────────────────
        def lookup_desconhecido(domain_id: str):
            raise KeyError(domain_id)

        api._domain_lookup = lookup_desconhecido
        try:
            asyncio.run(api.read_source("inexistente", "page.md", Response()))
            check("domínio desconhecido -> 404", False)
        except HTTPException as exc:
            check("domínio desconhecido -> 404", exc.status_code == 404)

        # ── domínio kind == 'tool' -> 404, sem chamar authorized_document ────────────
        chamou = []

        async def poison(*a, **kw):
            chamou.append((a, kw))
            raise AssertionError("authorized_document não deveria ser chamado")

        api._domain_lookup = lambda domain_id: domain_tool
        api.authorized_document = poison
        try:
            asyncio.run(api.read_source("platform", "page.md", Response()))
            check("domínio kind=='tool' -> 404", False)
        except HTTPException as exc:
            check("domínio kind=='tool' -> 404", exc.status_code == 404)
        check("domínio kind=='tool' não chama authorized_document", chamou == [])

        api._domain_lookup = lambda domain_id: domain_ok

        # ── PermissionError -> 403 ────────────────────────────────────────────────────
        async def nega(domain, name, user):
            exc = PermissionError("sem autorização")
            exc.url = "https://acct.blob.core.windows.net/c/page.md"
            raise exc

        api.authorized_document = nega
        try:
            asyncio.run(api.read_source("selfwiki", "page.md", Response()))
            check("PermissionError -> 403", False)
        except HTTPException as exc:
            check("PermissionError -> 403", exc.status_code == 403)

        # ── FileNotFoundError -> 404 ──────────────────────────────────────────────────
        async def nao_encontrado(domain, name, user):
            exc = FileNotFoundError(name)
            exc.url = "https://acct.blob.core.windows.net/c/page.md"
            raise exc

        api.authorized_document = nao_encontrado
        try:
            asyncio.run(api.read_source("selfwiki", "page.md", Response()))
            check("FileNotFoundError -> 404", False)
        except HTTPException as exc:
            check("FileNotFoundError -> 404", exc.status_code == 404)

        # ── NomeDocumentoInvalido -> 400 ──────────────────────────────────────────────
        async def nome_invalido(domain, name, user):
            raise NomeDocumentoInvalido(name)

        api.authorized_document = nome_invalido
        try:
            asyncio.run(api.read_source("selfwiki", "a/b.md", Response()))
            check("NomeDocumentoInvalido -> 400", False)
        except HTTPException as exc:
            check("NomeDocumentoInvalido -> 400", exc.status_code == 400)

        # ── ValueError genérico (não NomeDocumentoInvalido) NÃO vira 400 (M2) ─────────
        # `json.JSONDecodeError` é subclasse de `ValueError`; se a rota capturasse
        # `ValueError` também pegaria essa, disfarçando falha de infra de erro do cliente.
        async def infra_quebrada(domain, name, user):
            raise ValueError("corpo malformado do Search")

        api.authorized_document = infra_quebrada
        try:
            asyncio.run(api.read_source("selfwiki", "page.md", Response()))
            check("ValueError genérico não vira 400 (propaga)", False)
        except HTTPException as exc:
            check(f"ValueError genérico não vira 400 (veio HTTPException {exc.status_code})", False)
        except ValueError:
            check("ValueError genérico não vira 400 (propaga)", True)

        # ── caminho autorizado: Cache-Control: no-store ───────────────────────────────
        async def autorizado(domain, name, user):
            return ("https://acct.blob.core.windows.net/c/page.md", "conteúdo")

        api.authorized_document = autorizado
        resp = Response()
        resultado = asyncio.run(api.read_source("selfwiki", "page.md", resp))
        check("caminho autorizado devolve o conteúdo", resultado.get("content") == "conteúdo")
        check("Cache-Control: no-store no caminho autorizado", resp.headers.get("cache-control") == "no-store")

        # ── I2: o gate de entitlement só roda no modo shared ──────────────────────────
        chamadas_gate: list[str] = []

        def require_domain_espiao(domain_id: str):
            async def _check():
                chamadas_gate.append(domain_id)

            return _check

        api.require_domain = require_domain_espiao
        api.authorized_document = autorizado

        api.settings.deployment_mode = "self_hosted"
        asyncio.run(api.read_source("selfwiki", "page.md", Response()))
        check("modo self_hosted não chama o gate de entitlement", chamadas_gate == [])

        api.settings.deployment_mode = "shared"
        asyncio.run(api.read_source("selfwiki", "page.md", Response()))
        check("modo shared chama o gate de entitlement", chamadas_gate == ["selfwiki"])

        def require_domain_nega(domain_id: str):
            async def _check():
                raise HTTPException(status_code=403, detail="domínio não habilitado para o tenant")

            return _check

        api.require_domain = require_domain_nega
        chamou.clear()
        api.authorized_document = poison
        try:
            asyncio.run(api.read_source("selfwiki", "page.md", Response()))
            check("gate de entitlement nega -> 403 sem tocar authorized_document", False)
        except HTTPException as exc:
            check(
                "gate de entitlement nega -> 403 sem tocar authorized_document",
                exc.status_code == 403 and chamou == [],
            )
    finally:
        restaurar()

    print()
    if falhas:
        print(f"FALHOU: {len(falhas)} verificação(ões)")
        return 1
    print("tudo certo")
    return 0


if __name__ == "__main__":
    sys.exit(main())
