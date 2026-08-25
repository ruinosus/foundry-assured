"""O documento integral pelo MCP: mesma decisão de acesso da web, e caminho que não vira caminho.

Três propriedades, nenhuma delas confiada a reputação:

1. **O ACL é o do backend, não um novo.** Quem decide é
   `knowledge.public.authorized_document` — a MESMA função da rota `GET /source/{domain}/{name}`.
   O teste prova isso por substituição: quando ela nega, nada sai; quando ela permite, sai o que
   ela devolveu; e ela é chamada em TODA leitura (uma regra própria que respondesse antes dela
   apareceria aqui como uma leitura que não passou pela substituição).
2. **Caminho não vira caminho.** `..`, caminho absoluto e byte nulo são recusados — e o teste
   mede as DUAS barreiras separadamente, porque nenhuma depende da outra: o screening do
   FastMCP 4 (`resource_security`, ligado por padrão) e o `_NOME_OK` de `authorized_document`.
   Confiar no default sem prova é como não ter default: ninguém percebe quando ele muda.
3. **A trilha grava o par (ADR-023).** A leitura autorizada E a negada — a negada é o sinal
   mais interessante da trilha, e é a que costuma faltar.

    uv run python -m tests.resource_document_test
"""

from __future__ import annotations

import asyncio
import logging
import sys

from fastmcp import FastMCP
from fastmcp.exceptions import NotFoundError, ResourceError

from app.modules.audit import public as audit_public
from app.modules.knowledge.public import NomeDocumentoInvalido, authorized_document
from app.shared import auth as shared_auth
from app.shared.settings import settings
from mcp_app import resources_knowledge


class _Spec:
    """Um `DomainSpec` de mentira: o resource só lê `.kind` dele, o resto vai inteiro para o
    `authorized_document` — que aqui está substituído."""

    def __init__(self, domain_id: str, kind: str) -> None:
        self.id = domain_id
        self.kind = kind


_CATALOGO = [_Spec("techdocs", "grounded"), _Spec("selfwiki", "grounded"), _Spec("platform", "tool")]


class _Token:
    def __init__(self, raw: str) -> None:
        self.token = raw
        self.claims = {
            "roles": ["Reader"],
            "oid": "00000000-0000-0000-0000-0000000000aa",
            "preferred_username": "quem.perguntou@exemplo.invalid",
        }


def _servidor() -> FastMCP:
    """O servidor com o resource montado pelo `register` REAL, e com o mesmo
    `resource_security` que `mcp_app.main.build_mcp` usa — que é o default do FastMCP 4.

    Não passamos `resource_security=` aqui de propósito: se o app passasse um e o teste
    passasse outro, o teste provaria a política dele, não a do app.
    """
    mcp = FastMCP("resource-test", tools=[], mask_error_details=True)
    resources_knowledge.register(mcp)
    return mcp


def main() -> int:
    falhas: list[str] = []
    chamadas: list[tuple] = []
    eventos: list[dict] = []

    # O FastMCP loga `exception` em toda leitura recusada — e metade deste arquivo é leitura
    # recusada DE PROPÓSITO. Sem isto, a saída do gate é dominada por tracebacks de casos que
    # passaram, e o operador aprende a ignorar traceback no log do MCP. Restaurado no `finally`.
    logging.disable(logging.CRITICAL)

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    original = (
        resources_knowledge.authorized_document,
        resources_knowledge._token_do_chamador,
        resources_knowledge._domain_lookup,
        resources_knowledge._catalogo,
        audit_public.record,
        settings.entra_tenant_id,
        settings.entra_api_client_id,
    )

    def lookup(domain_id: str):
        for spec in _CATALOGO:
            if spec.id == domain_id:
                return spec
        raise KeyError(domain_id)

    def falso_record(scope, actor, kind, summary, ref="", detail=None):
        eventos.append(
            {"scope": scope, "actor": actor, "kind": kind, "summary": summary,
             "ref": ref, "detail": detail or {}}
        )
        return {}

    try:
        audit_public.record = falso_record
        resources_knowledge.set_domain_registry(lookup, lambda: list(_CATALOGO))
        resources_knowledge._token_do_chamador = lambda: _Token("token-do-chamador")
        # Auth DESLIGADA: `require_any_role` degrada aberto (dev local), o que mantém o resource
        # visível ao `get_resource_template` sem precisar de um Entra. O que este arquivo prova
        # é o ACL POR DOCUMENTO, que é independente do papel.
        settings.entra_tenant_id = ""
        settings.entra_api_client_id = ""

        mcp = _servidor()

        # ── 1 · quem decide é `authorized_document` ──────────────────────────────────────
        async def permite(domain, name, user):
            chamadas.append((getattr(domain, "id", None), name, getattr(user, "access_token", None)))
            return (f"https://conta.blob.core.windows.net/c/{name}", "# conteúdo autorizado")

        resources_knowledge.authorized_document = permite
        r = asyncio.run(mcp.read_resource("document://techdocs/page-11.md"))
        corpo = r.contents[0].content
        check("documento autorizado volta com conteúdo e URL", '"content": "# conte' in corpo and "conta.blob" in corpo)
        check(
            "a decisão passou por `authorized_document`, com o domínio e o nome resolvidos",
            chamadas and chamadas[-1][:2] == ("techdocs", "page-11.md"),
        )
        check(
            "e sob a identidade do CHAMADOR, não a da aplicação",
            chamadas[-1][2] == "token-do-chamador",
        )
        check(
            "a leitura autorizada entrou na trilha, com o ator certo (ADR-023)",
            eventos
            and eventos[-1]["detail"].get("authorized") is True
            and eventos[-1]["actor"] == "human:quem.perguntou@exemplo.invalid",
        )

        # ── 1b · quando ela nega, NADA sai ───────────────────────────────────────────────
        async def nega(domain, name, user):
            chamadas.append((getattr(domain, "id", None), name, "NEGADO"))
            exc = PermissionError(f"sem autorização de leitura para {name}")
            exc.url = f"https://conta.blob.core.windows.net/c/{name}"
            raise exc

        resources_knowledge.authorized_document = nega
        eventos.clear()
        try:
            asyncio.run(mcp.read_resource("document://techdocs/secreto.md"))
            check("documento sem autorização NÃO é servido", False)
        except ResourceError as exc:
            print(f"     ResourceError: {exc}")
            check(
                "documento sem autorização NÃO é servido (e o motivo não conta se ele existe)",
                "sem autorização" in str(exc) and "secreto.md" not in str(exc),
            )
        check(
            "a NEGATIVA também entra na trilha, com a URL do documento",
            eventos
            and eventos[-1]["detail"].get("authorized") is False
            and "secreto.md" in str(eventos[-1]["detail"].get("url")),
        )

        # ── 1c · os outros dois erros da rota `/source`, com o mesmo mapeamento ──────────
        async def nome_ruim(domain, name, user):
            raise NomeDocumentoInvalido(f"nome de documento inválido: {name!r}")

        resources_knowledge.authorized_document = nome_ruim
        try:
            asyncio.run(mcp.read_resource("document://techdocs/nome-que-nao-serve"))
            check("nome inválido é recusado", False)
        except ResourceError as exc:
            check("nome inválido → 'nome de documento inválido'", "nome de documento inválido" in str(exc))

        async def sumido(domain, name, user):
            exc = FileNotFoundError(name)
            exc.url = "https://conta.blob.core.windows.net/c/x"
            raise exc

        resources_knowledge.authorized_document = sumido
        try:
            asyncio.run(mcp.read_resource("document://techdocs/inexistente.md"))
            check("documento inexistente é recusado", False)
        except ResourceError as exc:
            check("documento inexistente → 'documento não encontrado'", "não encontrado" in str(exc))

        # ── 1d · domínio `tool` não tem documento — mesma recusa da rota `/source` ───────
        async def envenenado(domain, name, user):
            raise AssertionError("authorized_document não deveria ser chamado")

        resources_knowledge.authorized_document = envenenado
        for uri, esperado in (
            ("document://platform/x.md", "domínio não tem documentos"),
            ("document://nao-existe/x.md", "domínio desconhecido"),
        ):
            try:
                asyncio.run(mcp.read_resource(uri))
                check(f"{uri} é recusado antes de tocar o documento", False)
            except ResourceError as exc:
                check(f"{uri} → {esperado!r}, sem tocar o documento", esperado in str(exc))

        # ── 2 · caminho não vira caminho — BARREIRA 1: o screening do FastMCP 4 ──────────
        # `authorized_document` continua envenenado: se qualquer payload chegasse ao handler,
        # o AssertionError apareceria em vez da recusa.
        payloads = {
            "traversal `..` (literal)": "document://techdocs/../secreto.md",
            "traversal `..` (percent-encoded)": "document://techdocs/%2E%2E%2Fsecreto.md",
            "caminho absoluto": "document://techdocs/%2Fetc%2Fpasswd",
            "byte nulo": "document://techdocs/a%00.md",
        }
        for rotulo, uri in payloads.items():
            try:
                asyncio.run(mcp.read_resource(uri))
                check(f"barreira 1 · {rotulo} recusado", False)
            except (NotFoundError, ResourceError) as exc:
                print(f"     {type(exc).__name__}: {exc}")
                check(f"barreira 1 · {rotulo} recusado ({type(exc).__name__})", True)

        # ── 2b · BARREIRA 2: o `_NOME_OK` do próprio `authorized_document` ───────────────
        # Independente da primeira: mesmo que um dia o screening do FastMCP mude de default,
        # o backend continua recusando um nome que não é nome de blob — ANTES de qualquer I/O.
        for rotulo, nome in (
            ("traversal `..`", "../secreto.md"),
            ("caminho absoluto", "/etc/passwd"),
            ("byte nulo", "a\x00.md"),
        ):
            try:
                asyncio.run(authorized_document(_Spec("techdocs", "grounded"), nome, None))
                check(f"barreira 2 · {rotulo} recusado pelo backend", False)
            except NomeDocumentoInvalido:
                check(f"barreira 2 · {rotulo} recusado pelo backend (NomeDocumentoInvalido)", True)
            except Exception as exc:  # noqa: BLE001 — qualquer outra coisa é a notícia
                check(f"barreira 2 · {rotulo} recusado pelo backend (veio {type(exc).__name__})", False)
    finally:
        (
            resources_knowledge.authorized_document,
            resources_knowledge._token_do_chamador,
            resources_knowledge._domain_lookup,
            resources_knowledge._catalogo,
            audit_public.record,
            settings.entra_tenant_id,
            settings.entra_api_client_id,
        ) = original
        shared_auth._current_user.set(None)
        logging.disable(logging.NOTSET)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o documento integral pelo MCP decide pelo mesmo ACL da web, e o nome nunca vira caminho.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
