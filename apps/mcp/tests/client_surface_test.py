"""Um CLIENTE MCP de verdade lista os prompts, lê o documento — e não enxerga o que não é dele.

O SEGUNDO CRITÉRIO DE PRONTO DA FASE 1 ("um cliente lista prompts e lê um resource com ACL
aplicada") não era exercitado por gate nenhum. `authz_test` prova a FUNÇÃO de decisão
(`require_any_role`) contra contextos montados à mão; a matriz prova que o `auth=` EXISTE em cada
superfície. Nenhum dos dois prova que o FastMCP de fato FILTRA — que a decisão chega ao
protocolo. Entre a função certa e o comportamento certo há uma pilha inteira: middleware de auth,
`_get_auth_context`, o filtro de cada `list_*`, o `read_resource`. Este gate atravessa ela.

O QUE ELE ATRAVESSA, E POR QUE ISSO CABE NUM GATE OFFLINE. O servidor é o que `build_app()` monta
(a MESMA fábrica que o `uvicorn` sobe — nenhuma montagem paralela), servido por
`httpx2.ASGITransport`: pilha HTTP completa, em processo, sem socket, sem daemon e sem rede. O
cliente é o `fastmcp.Client` de verdade, falando streamable HTTP com o servidor pelo mesmo
transporte. Nada aqui é simulado a não ser as três coisas que TÊM que ser: o verificador de token
(um `StaticTokenVerifier` no lugar do `AzureJWTVerifier`, que buscaria as chaves do Entra pela
rede), o catálogo de domínios e o `authorized_document` — os dois últimos pelos mesmos seams que
os outros gates deste app já usam.

O PARZINHO É O PONTO: dois chamadores, mesma pilha, tokens diferentes.

    tok-reader  →  `roles: ["Reader"]`  →  vê a tool, os prompts e o resource; LÊ o documento
    tok-nenhum  →  `roles: []`          →  não vê NADA disso, e a leitura direta é recusada

Um chamador sem papel não recebe erro na listagem: as superfícies simplesmente não existem para
ele (`fastmcp/server/server.py:879` — componente negado por `auth=` é FILTRADO, não recusado). É
por isso que a asserção é sobre a LISTA e não sobre uma exceção: um teste que só esperasse erro
passaria feliz num servidor que devolvesse tudo para todo mundo mas explodisse na chamada.

    uv run python -m tests.client_surface_test
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import httpx2
import mcp_types
from fastmcp import Client
from fastmcp.client.transports.http import StreamableHttpTransport
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier

from app.shared import auth as shared_auth
from app.shared.settings import ENTRA_API_SCOPE_NAME, settings
from mcp_app import main as mcp_main
from mcp_app import resources_knowledge
from mcp_app.auth import MCP_PATH

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
BASE = "http://testserver"

#: Os dois chamadores. Mesmo escopo, mesma app registration, mesma pilha — a ÚNICA diferença é o
#: claim `roles`, que é onde a decisão mora (`mcp_app.auth._papeis_do_entra`).
TOKENS = {
    "tok-reader": {
        "client_id": CLIENT_ID,
        "scopes": [ENTRA_API_SCOPE_NAME],
        "roles": ["Reader"],
        "oid": "00000000-0000-0000-0000-0000000000aa",
        "preferred_username": "com.papel@exemplo.invalid",
    },
    "tok-nenhum": {
        "client_id": CLIENT_ID,
        "scopes": [ENTRA_API_SCOPE_NAME],
        "roles": [],
        "oid": "00000000-0000-0000-0000-0000000000bb",
        "preferred_username": "sem.papel@exemplo.invalid",
    },
}


class _Spec:
    def __init__(self, domain_id: str, kind: str) -> None:
        self.id = domain_id
        self.kind = kind


_CATALOGO = [_Spec("techdocs", "grounded"), _Spec("selfwiki", "grounded")]


def _lookup(domain_id: str):
    for spec in _CATALOGO:
        if spec.id == domain_id:
            return spec
    raise KeyError(domain_id)


def _auth_estatico(_base_url: str):
    """O provider que substitui `build_auth` — mesma classe (`RemoteAuthProvider`), mesmo
    caminho de middleware, só o verificador é estático.

    `AzureJWTVerifier` buscaria o JWKS do Entra na primeira requisição, o que tiraria este gate
    de `DEFAULT_JOBS` (`scripts/gates.py` promete offline e determinístico). O que está sob teste
    é o que acontece DEPOIS da verificação — as claims virando (ou não) acesso.
    """
    return RemoteAuthProvider(
        token_verifier=StaticTokenVerifier(TOKENS),
        authorization_servers=[f"https://login.microsoftonline.com/{TENANT}/v2.0"],
        base_url=BASE,
        resource_name="Foundry Assured MCP",
    )


def _cliente(app, token: str) -> Client:
    """Um `Client` de verdade, falando com o app ASGI em processo (nenhum socket)."""

    def fabrica(**kwargs):
        kwargs.pop("verify", None)
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=BASE, **kwargs
        )

    return Client(
        StreamableHttpTransport(url=BASE + MCP_PATH, auth=token, httpx_client_factory=fabrica)
    )


async def _visao(app, token: str) -> dict:
    """O que este chamador ENXERGA e CONSEGUE, em uma sessão."""
    async with _cliente(app, token) as client:
        visao = {
            "tools": sorted(t.name for t in await client.list_tools()),
            "prompts": sorted(p.name for p in await client.list_prompts()),
            "templates": sorted(t.uri_template for t in await client.list_resource_templates()),
        }
        try:
            r = await client.read_resource("document://techdocs/page-11.md")
            # O corpo vem como JSON (o `mime_type` do template): o conteúdo é o CAMPO, não a
            # serialização. Comparar contra o texto cru passaria a acertar/errar por causa do
            # escape unicode do `json.dumps`, que não tem nada a ver com o que está sob teste.
            visao["documento"] = json.loads(r[0].text)["content"]
        except Exception as exc:  # noqa: BLE001 — a recusa É o resultado sob teste
            visao["documento"] = f"RECUSADO {type(exc).__name__}: {exc}"
        completado = await client.complete(
            mcp_types.ResourceTemplateReference(uri=resources_knowledge.URI_DOCUMENTO),
            {"name": "domain", "value": ""},
        )
        visao["completion"] = sorted(completado.values)
        return visao


def main() -> int:
    falhas: list[str] = []

    # O FastMCP loga `exception` em toda recusa, e metade deste arquivo é recusa DE PROPÓSITO.
    logging.disable(logging.CRITICAL)

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    original = (
        mcp_main.build_auth,
        resources_knowledge.authorized_document,
        resources_knowledge._domain_lookup,
        resources_knowledge._catalogo,
        resources_knowledge._template,
        settings.entra_tenant_id,
        settings.entra_api_client_id,
        settings.mcp_public_base_url,
    )

    async def permite(domain, name, user):
        return (f"https://conta.blob.core.windows.net/c/{name}", "# conteúdo autorizado")

    try:
        settings.entra_tenant_id = TENANT
        settings.entra_api_client_id = CLIENT_ID
        settings.mcp_public_base_url = BASE
        mcp_main.build_auth = _auth_estatico

        # A fábrica REAL. `wire_registry` roda dentro dela e empurra o catálogo de verdade; os
        # seams abaixo o substituem em seguida, para que nada aqui dependa de config do Azure.
        app = mcp_main.build_app()
        resources_knowledge.set_domain_registry(_lookup, lambda: list(_CATALOGO))
        resources_knowledge.authorized_document = permite

        async def roda():
            # O lifespan é obrigatório aqui (e só aqui): é ele que sobe o session manager do
            # streamable HTTP. Sem `AzureJWTVerifier` ele não faz rede nenhuma.
            async with app.router.lifespan_context(app):
                com = await _visao(app, "tok-reader")
                sem = await _visao(app, "tok-nenhum")
                return com, sem

        com, sem = asyncio.run(roda())

        print(f"     COM papel : {com['tools']} · {len(com['prompts'])} prompts · {com['templates']}")
        print(f"     DOC       : {com['documento']!r}")
        print(f"     SEM papel : {sem['tools']} · {len(sem['prompts'])} prompts · {sem['templates']}")

        # ── o chamador COM papel: vê e consegue ─────────────────────────────────────────
        check("com papel · a tool `search_docs` aparece", com["tools"] == ["search_docs"])
        check(
            f"com papel · os prompts do produto aparecem ({len(com['prompts'])})",
            len(com["prompts"]) > 0,
        )
        check(
            "com papel · o template do documento aparece",
            com["templates"] == [resources_knowledge.URI_DOCUMENTO],
        )
        check(
            "com papel · LÊ o documento pelo protocolo, com o ACL do backend aplicado",
            "conteúdo autorizado" in str(com["documento"]),
        )
        check(
            f"com papel · a completion sugere os domínios ({com['completion']})",
            com["completion"] == ["selfwiki", "techdocs"],
        )

        # ── o chamador SEM papel: nada disso existe para ele ────────────────────────────
        check("sem papel · nenhuma tool na listagem", sem["tools"] == [])
        check("sem papel · nenhum prompt na listagem", sem["prompts"] == [])
        check("sem papel · nenhum template na listagem", sem["templates"] == [])
        check(
            f"sem papel · a leitura direta é recusada ({str(sem['documento'])[:60]})",
            str(sem["documento"]).startswith("RECUSADO"),
        )
        check(
            "sem papel · e a completion não sugere nada (o gate que o FastMCP não roda)",
            sem["completion"] == [],
        )
        check(
            "o conteúdo NÃO vazou pela recusa",
            "conteúdo autorizado" not in str(sem["documento"]),
        )
    finally:
        (
            mcp_main.build_auth,
            resources_knowledge.authorized_document,
            resources_knowledge._domain_lookup,
            resources_knowledge._catalogo,
            resources_knowledge._template,
            settings.entra_tenant_id,
            settings.entra_api_client_id,
            settings.mcp_public_base_url,
        ) = original
        shared_auth._current_user.set(None)
        logging.disable(logging.NOTSET)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ um cliente real lista prompts e lê o documento; sem papel, nada disso existe.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
