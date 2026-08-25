"""O documento integral pelo MCP: mesma decisão de acesso da web, e caminho que não vira caminho.

Três propriedades, nenhuma delas confiada a reputação:

1. **O ACL é o do backend, não um novo.** Quem decide é
   `knowledge.public.authorized_document` — a MESMA função da rota `GET /source/{domain}/{name}`.
   O teste prova isso por substituição: quando ela nega, nada sai; quando ela permite, sai o que
   ela devolveu; e ela é chamada em TODA leitura (uma regra própria que respondesse antes dela
   apareceria aqui como uma leitura que não passou pela substituição).
2. **Caminho não vira caminho.** `..`, caminho absoluto e byte nulo são recusados — e o teste
   mede TRÊS mecanismos separadamente, porque nenhum depende do outro, e cada asserção nomeia
   o mecanismo que de fato respondeu:
      - **roteamento**: um `..` LITERAL na URI não casa com o template e volta `NotFoundError`.
        Este arquivo já rotulou esse caso como "barreira 1" (o screening); estava errado, e um
        teste que atribui a defesa ao mecanismo errado ensina errado — quem lesse acharia que o
        `resource_security` cobre um caso que ele nunca chega a ver.
      - **`resource_security`** (o default do FastMCP 4): `..` percent-encoded, caminho absoluto
        e byte nulo chegam ao roteamento, casam com o template e são recusados no screening dos
        parâmetros extraídos, com `ResourceSecurityError`.
      - **`_NOME_OK`** dentro de `authorized_document`: o backend recusa o nome antes de qualquer
        I/O, mesmo que um dia o default do FastMCP mude.
   Confiar no default sem prova é como não ter default: ninguém percebe quando ele muda.
3. **A trilha grava o par (ADR-023).** A leitura autorizada E a negada — a negada é o sinal
   mais interessante da trilha, e é a que costuma faltar.
4. **No modo `shared`, o tenant é resolvido e o entitlement é cobrado (ADR-010).** Os dois
   ramos foram medidos e os dois eram ruins antes disto: com tenant resolvido SEM licença para
   o domínio, o resource servia o conteúdo; e sem tenant nenhum — o estado real do `shared`,
   porque só a tool `search_docs` resolvia — toda leitura virava "domínio desconhecido". O
   resource estava morto no `shared`, disfarçado de erro de domínio. A recusa por entitlement
   diz ENTITLEMENT, com a mesma mensagem exata da tool, para que as duas causas não se
   confundam.

    uv run python -m tests.resource_document_test
"""

from __future__ import annotations

import asyncio
import logging
import sys

from fastmcp import FastMCP
from fastmcp.exceptions import NotFoundError, ResourceError, ResourceSecurityError

from app.modules.audit import public as audit_public
from app.modules.knowledge.public import NomeDocumentoInvalido, authorized_document
from app.modules.tenancy.public import current_tenant_id, set_current_tenant
from app.shared import auth as shared_auth
from app.shared.settings import settings
from mcp_app import resources_knowledge, tenant_gate


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
        settings.deployment_mode,
    )

    def lookup(domain_id: str):
        """O `domain_spec` de mentira — mas com a MESMA dependência de tenant que o de verdade.

        `domain_spec` percorre `domain_specs()`, que lê `tenant_config()`; no modo `shared` o
        provider é o `MultiTenantConfigProvider`, e ele levanta `RuntimeError("no tenant resolved
        for this request")` quando nenhum tenant está resolvido
        (`tenancy/internal/tenant.py:199`). Um lookup de teste que ignorasse isso ficaria verde
        sobre o defeito principal: era EXATAMENTE essa exceção que virava, em `_resolver`,
        "domínio desconhecido" — a leitura por MCP morta no `shared`, disfarçada de erro de
        domínio, porque só a tool `search_docs` resolvia tenant.
        """
        if settings.deployment_mode == "shared" and current_tenant_id() is None:
            raise RuntimeError("no tenant resolved for this request")
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

        # ── 2 · caminho não vira caminho — CADA UM COM O SEU MECANISMO ──────────────────
        # `authorized_document` continua envenenado: se qualquer payload chegasse ao handler,
        # o AssertionError apareceria em vez da recusa.
        #
        # O TIPO DA EXCEÇÃO É A ASSERÇÃO, e não um detalhe impresso ao lado: é ele que diz QUEM
        # recusou. Aceitar `(NotFoundError, ResourceError)` para todos, como este arquivo fazia,
        # deixava passar a troca de um mecanismo por outro sem ninguém notar — e foi assim que o
        # `..` literal ficou rotulado como screening quando quem o recusa é o roteamento.
        payloads = {
            # NÃO casa com `document://{domain}/{name}`: a barra a mais faz o template não
            # bater, e o screening dos parâmetros nunca chega a rodar. Roteamento, não política.
            "roteamento · traversal `..` (literal)": (
                "document://techdocs/../secreto.md",
                NotFoundError,
            ),
            # Estes três CASAM com o template (o `%2F` não é separador de caminho na URI) e são
            # recusados pelo `resource_security` do FastMCP 4, ligado por padrão.
            "resource_security · traversal `..` (percent-encoded)": (
                "document://techdocs/%2E%2E%2Fsecreto.md",
                ResourceSecurityError,
            ),
            "resource_security · caminho absoluto": (
                "document://techdocs/%2Fetc%2Fpasswd",
                ResourceSecurityError,
            ),
            "resource_security · byte nulo": (
                "document://techdocs/a%00.md",
                ResourceSecurityError,
            ),
        }
        for rotulo, (uri, esperado) in payloads.items():
            try:
                asyncio.run(mcp.read_resource(uri))
                check(f"{rotulo} recusado", False)
            except Exception as exc:  # noqa: BLE001 — o TIPO é o que está sob teste
                print(f"     {type(exc).__name__}: {exc}")
                # `type(...) is`, não `isinstance`: `ResourceSecurityError` HERDA de
                # `NotFoundError`, então um `isinstance` deixaria o caso de roteamento passar
                # também quando quem respondesse fosse o screening — apagando justamente a
                # distinção que estas quatro linhas existem para fazer.
                check(
                    f"{rotulo} recusado por {esperado.__name__}"
                    + (f" — veio {type(exc).__name__}" if type(exc) is not esperado else ""),
                    type(exc) is esperado,
                )

        # ── 2b · O `_NOME_OK` do próprio `authorized_document` ──────────────────────────
        # Independente dos dois acima: mesmo que um dia o screening do FastMCP mude de default,
        # o backend continua recusando um nome que não é nome de blob — ANTES de qualquer I/O.
        for rotulo, nome in (
            ("traversal `..`", "../secreto.md"),
            ("caminho absoluto", "/etc/passwd"),
            ("byte nulo", "a\x00.md"),
        ):
            try:
                asyncio.run(authorized_document(_Spec("techdocs", "grounded"), nome, None))
                check(f"_NOME_OK · {rotulo} recusado pelo backend", False)
            except NomeDocumentoInvalido:
                check(f"_NOME_OK · {rotulo} recusado pelo backend (NomeDocumentoInvalido)", True)
            except Exception as exc:  # noqa: BLE001 — qualquer outra coisa é a notícia
                check(f"_NOME_OK · {rotulo} recusado pelo backend (veio {type(exc).__name__})", False)

        # ── 3 · modo `shared`: tenant resolvido, entitlement cobrado (ADR-010) ──────────
        # A MESMA regra da tool (`mcp_app.tenant_gate`), agora com o resource como consumidor.
        class _Registro:
            def __init__(self, tid, enabled, status="active"):
                self.tid = tid
                self.enabled_domains = enabled
                self.status = status

        class _TokenTenant:
            def __init__(self, tid):
                self.token = "token-do-chamador"
                self.claims = {"roles": ["Reader"], "oid": "o-1", "tid": tid,
                               "preferred_username": "quem.perguntou@exemplo.invalid"}

        loja = {
            "t-ok": _Registro("t-ok", ("techdocs",)),
            "t-sem": _Registro("t-sem", ("selfwiki",)),
        }
        # Auth continua DESLIGADA (como no resto do arquivo) de propósito: com ela ligada e
        # sem token no contexto do FastMCP, `read_resource` FILTRA o template pelo `auth=` e
        # devolve `NotFoundError: Unknown resource` — medido — e o que este bloco prova
        # (tenant + entitlement) ficaria escondido atrás do gate de papel. Quem prova o gate de
        # papel sob HTTP real, com token, é `tests/client_surface_test.py`.
        settings.deployment_mode = "shared"
        tenant_gate.set_tenant_store(lambda tid: loja.get(tid))
        resources_knowledge.authorized_document = permite

        # 3a · O RESOURCE FUNCIONA NO SHARED. Antes disto não funcionava: nada aqui chamava
        # `resolve_tenant_record`, então `_resolver` levantava e TODA leitura virava "domínio
        # desconhecido" — o resource morto, disfarçado de erro de domínio.
        resources_knowledge._token_do_chamador = lambda: _TokenTenant("t-ok")
        chamadas.clear()
        try:
            r = asyncio.run(mcp.read_resource("document://techdocs/page-11.md"))
            check(
                "shared · tenant licenciado LÊ o documento (antes: 'domínio desconhecido')",
                '"content": "# conte' in r.contents[0].content,
            )
        except Exception as exc:  # noqa: BLE001 — a exceção É o defeito que isto conserta
            check(f"shared · tenant licenciado LÊ o documento — veio {type(exc).__name__}: {exc}", False)

        # 3b · domínio não licenciado é RECUSADO, e a recusa diz ENTITLEMENT.
        # Mensagem EXATA, não substring, e a mesma da tool: "tenant não habilitado" também
        # contém "não habilitado", e "domínio desconhecido" confundiria as duas causas — que é
        # exatamente o que este resource fazia quando não resolvia tenant nenhum.
        resources_knowledge._token_do_chamador = lambda: _TokenTenant("t-sem")
        eventos.clear()
        try:
            asyncio.run(mcp.read_resource("document://techdocs/page-11.md"))
            check("shared · domínio NÃO licenciado é recusado", False)
        except ResourceError as exc:
            print(f"     ResourceError: {exc}")
            check(
                "shared · domínio NÃO licenciado é recusado, com a mensagem do entitlement",
                str(exc) == "domínio não habilitado para o tenant: techdocs",
            )
        check(
            "shared · a negativa por entitlement TAMBÉM entra na trilha (a rota /source já fazia)",
            eventos and eventos[-1]["detail"].get("authorized") is False,
        )

        # 3c · tenant desconhecido: recusado antes de qualquer coisa.
        resources_knowledge._token_do_chamador = lambda: _TokenTenant("t-inexistente")
        try:
            asyncio.run(mcp.read_resource("document://techdocs/page-11.md"))
            check("shared · tenant desconhecido é recusado", False)
        except ResourceError as exc:
            check("shared · tenant desconhecido é recusado", str(exc) == "tenant não habilitado")

        settings.deployment_mode = "self_hosted"
        tenant_gate.set_tenant_store(None)
        set_current_tenant(None)
    finally:
        (
            resources_knowledge.authorized_document,
            resources_knowledge._token_do_chamador,
            resources_knowledge._domain_lookup,
            resources_knowledge._catalogo,
            audit_public.record,
            settings.entra_tenant_id,
            settings.entra_api_client_id,
            settings.deployment_mode,
        ) = original
        tenant_gate.set_tenant_store(None)
        set_current_tenant(None)
        shared_auth._current_user.set(None)
        logging.disable(logging.NOTSET)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o documento integral pelo MCP decide pelo mesmo ACL da web, e o nome nunca vira caminho.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
