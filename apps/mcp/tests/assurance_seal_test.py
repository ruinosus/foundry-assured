"""O SELO DE ASSURANCE, provado no fio — nos dois sentidos do opt-in, sem inventar e sem vazar.

Este é o gate da camada que motivou separar o MCP num app próprio (ADR-027). Ele responde às
três perguntas que decidem se o selo vale alguma coisa, e responde MEDINDO, não afirmando:

    1. NEGOCIADO       quem anuncia a extensão recebe o selo; quem não anuncia recebe a resposta
                       IDÊNTICA à de antes desta fase — e "idêntica" aqui é comparação contra um
                       servidor montado SEM a extensão, não contra uma expectativa escrita à mão.
    2. NÃO INVENTA     cada campo do selo vem de uma fonte que já existia. A prova é por MUTAÇÃO:
                       muda-se a fonte e mostra-se o selo mudando junto. Um selo que continuasse
                       igual com a fonte mutada estaria fabricando.
    3. NÃO VAZA        o selo é metadado SOBRE a resposta. Com um chamador que não pode ler nada,
                       o evento que a trilha grava nomeia o documento negado — e o selo tem que
                       carregar o id do evento sem carregar o nome.

COMO ISTO CABE NUM GATE OFFLINE. Mesmo arranjo de `tests/client_surface_test.py`: o servidor é o
que `build_app()` monta (a MESMA fábrica que o `uvicorn` sobe), servido por
`httpx2.ASGITransport` — pilha HTTP inteira, em processo, sem socket, sem daemon e sem rede. O
cliente é o `fastmcp.Client` de verdade, e o opt-in usa `mcp.client.extension.advertise`, que é
o mecanismo do SDK para anunciar uma extensão sem implementá-la do lado do cliente. Simulados
apenas: o verificador de token (estático, no lugar do `AzureJWTVerifier`, que buscaria o JWKS do
Entra pela rede) e o `retrieve` (que falaria com o Azure Search). A TRILHA É REAL: sem
`AZURE_STORAGE_ACCOUNT` ela cai no `InMemoryTrail`, encadeia por hash igual à de produção, e é
dela que sai o id que o selo publica.

O `retrieve` falso GRAVA O EVENTO, exatamente como o de verdade grava
(`knowledge/internal/retrieval.py`, bloco "REGISTRO DE ACESSO"). Não é cerimônia: se ele não
gravasse, o teste provaria um selo com o campo de trilha sempre ausente, que é o defeito que
ele existe para pegar.

    uv run python -m tests.assurance_seal_test
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys

import httpx2
from fastmcp import Client
from fastmcp.client.transports.http import StreamableHttpTransport
from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.jwt import StaticTokenVerifier
from fastmcp.tools.base import ToolResult
from mcp.client.extension import advertise

from app.modules.audit import public as audit
from app.shared import auth as shared_auth
from app.shared.settings import ENTRA_API_SCOPE_NAME, settings
from mcp_app import assurance_extension, tools_knowledge
from mcp_app import main as mcp_main
from mcp_app.assurance_extension import CHAVE_DO_SELO, IDENTIFICADOR

TENANT = "11111111-1111-1111-1111-111111111111"
CLIENT_ID = "22222222-2222-2222-2222-222222222222"
BASE = "http://testserver"

#: O nome que NUNCA pode aparecer no selo. É o documento que o chamador sem acesso tentou abrir:
#: a trilha o registra (é o que uma trilha serve para fazer), e o selo não pode republicá-lo.
DOCUMENTO_RESERVADO = "runbook-secreto.md"

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

#: As linhas que o `retrieve` falso devolve no caminho feliz. Os `source`/`url` daqui são os
#: mesmos que o selo tem que republicar — é essa igualdade que prova a cópia.
LINHAS = [
    {"index": 1, "source": "page-11.md", "url": "https://conta/c/page-11.md", "snippet": "um"},
    {"index": 2, "source": "page-42.md", "url": "https://conta/c/page-42.md", "snippet": "dois"},
]


def _auth_estatico(_base_url: str):
    return RemoteAuthProvider(
        token_verifier=StaticTokenVerifier(TOKENS),
        authorization_servers=[f"https://login.microsoftonline.com/{TENANT}/v2.0"],
        base_url=BASE,
        resource_name="Foundry Assured MCP",
    )


def _cliente(app, token: str, *, negocia: bool) -> Client:
    """Um `Client` de verdade. `negocia=True` anuncia a extensão; `False` não anuncia nada.

    `advertise` é o mecanismo do SDK para declarar uma extensão sem implementá-la do lado do
    cliente — e é exatamente o que um cliente que só quer LER o selo faria.
    """

    def fabrica(**kwargs):
        kwargs.pop("verify", None)
        return httpx2.AsyncClient(
            transport=httpx2.ASGITransport(app=app), base_url=BASE, **kwargs
        )

    return Client(
        StreamableHttpTransport(url=BASE + "/mcp/", auth=token, httpx_client_factory=fabrica),
        extensions=[advertise(IDENTIFICADOR)] if negocia else None,
    )


def _selo(resultado) -> dict | None:
    """O selo dentro do `_meta` do resultado, ou `None` quando ele não veio."""
    meta = getattr(resultado, "meta", None) or {}
    return meta.get(CHAVE_DO_SELO)


def _de_fio(resultado) -> dict:
    """O resultado INTEIRO como o cliente o recebeu, em forma comparável.

    Nada é removido de propósito — nem a chave do selo. É a asserção mais forte que este arquivo
    faz: se o servidor com a extensão carimbasse um cliente que não negociou, a comparação com o
    servidor sem a extensão quebraria aqui. `_meta` entra inteiro (inclusive o `serverInfo` que o
    próprio FastMCP anexa), porque o que se quer provar é que o fio não mudou, e não que ele
    mudou pouco.

    `CallToolResult` do cliente é uma dataclass com blocos Pydantic dentro; a serialização por
    bloco é só para poder comparar por igualdade de valor.
    """
    return {
        "content": [json.loads(b.model_dump_json()) for b in resultado.content],
        "structured_content": resultado.structured_content,
        "data": resultado.data,
        "is_error": resultado.is_error,
        "meta": resultado.meta,
    }


def main() -> int:
    falhas: list[str] = []
    gravado: dict = {}

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    logging.disable(logging.CRITICAL)

    original = (
        mcp_main.build_auth,
        tools_knowledge.retrieve,
        settings.entra_tenant_id,
        settings.entra_api_client_id,
        settings.mcp_public_base_url,
    )

    async def retrieve_com_trilha(query, user, domain, *, top=8):
        """O `retrieve` de verdade, menos o Azure: devolve linhas E grava o acesso na trilha.

        O bloco de `record` é o mesmo de `knowledge/internal/retrieval.py`, com os mesmos campos
        — inclusive o `documents` no detalhe, que é o que o selo NÃO pode deixar escapar.
        """
        linhas = gravado.get("linhas", LINHAS)
        if gravado.get("grava", True):
            gravado["evento"] = audit.record(
                scope="access",
                actor=audit.actor(),
                kind="access",
                summary=f"{len(linhas)} documento(s) recuperados",
                ref=getattr(domain, "id", "") or "techdocs",
                detail={
                    "documents": gravado.get("documentos") or [l["source"] for l in linhas],
                    "query_chars": len(query),
                    **audit.actor_detail(),
                },
            )
        return linhas

    try:
        settings.entra_tenant_id = TENANT
        settings.entra_api_client_id = CLIENT_ID
        settings.mcp_public_base_url = BASE
        mcp_main.build_auth = _auth_estatico
        tools_knowledge.retrieve = retrieve_com_trilha

        # DOIS APPS, e o segundo é o ponto de comparação da regra 1 do protocolo: ele é este
        # mesmo produto SEM a extensão, isto é, o servidor de ANTES desta fase. Comparar contra
        # ele é a única forma de dizer "idêntica" sem escrever à mão o que se espera.
        com_extensao = mcp_main.build_app()
        registro_real = assurance_extension.register
        try:
            assurance_extension.register = lambda _mcp: None
            sem_extensao = mcp_main.build_app()
        finally:
            assurance_extension.register = registro_real

        async def roda():
            saida = {}
            async with com_extensao.router.lifespan_context(com_extensao):
                async with _cliente(com_extensao, "tok-reader", negocia=True) as c:
                    saida["negociado"] = await c.call_tool(
                        "search_docs", {"domain": "techdocs", "query": "como reiniciar"}
                    )
                    saida["evento_negociado"] = dict(gravado.get("evento") or {})

                async with _cliente(com_extensao, "tok-reader", negocia=False) as c:
                    saida["mudo"] = await c.call_tool(
                        "search_docs", {"domain": "techdocs", "query": "como reiniciar"}
                    )

                # ── mutação 1: a fonte das CITAÇÕES muda (o trim não deixa nada passar) ──
                gravado["linhas"] = []
                gravado["documentos"] = []
                async with _cliente(com_extensao, "tok-reader", negocia=True) as c:
                    saida["sem_fonte"] = await c.call_tool(
                        "search_docs", {"domain": "techdocs", "query": "nada autorizado"}
                    )

                # ── mutação 2: a fonte da TRILHA some (nenhum evento gravado) ────────────
                gravado["linhas"] = LINHAS
                gravado["documentos"] = None
                gravado["grava"] = False
                async with _cliente(com_extensao, "tok-reader", negocia=True) as c:
                    saida["sem_trilha"] = await c.call_tool(
                        "search_docs", {"domain": "techdocs", "query": "sem trilha"}
                    )

                # ── vazamento: o chamador não lê nada, e a trilha nomeia o que ele tentou ─
                gravado["grava"] = True
                gravado["linhas"] = []
                gravado["documentos"] = [DOCUMENTO_RESERVADO]
                async with _cliente(com_extensao, "tok-reader", negocia=True) as c:
                    saida["negado"] = await c.call_tool(
                        "search_docs", {"domain": "techdocs", "query": "o que não é meu"}
                    )
                    saida["evento_negado"] = dict(gravado.get("evento") or {})

                # ── sem papel: a tool não existe para ele, então não há selo nenhum ──────
                gravado["linhas"] = LINHAS
                gravado["documentos"] = None
                async with _cliente(com_extensao, "tok-nenhum", negocia=True) as c:
                    try:
                        await c.call_tool(
                            "search_docs", {"domain": "techdocs", "query": "x"}
                        )
                        saida["sem_papel"] = "PASSOU"
                    except Exception as exc:  # noqa: BLE001 — a recusa É o resultado sob teste
                        saida["sem_papel"] = f"RECUSADO {type(exc).__name__}"

            async with (
                sem_extensao.router.lifespan_context(sem_extensao),
                _cliente(sem_extensao, "tok-reader", negocia=False) as c,
            ):
                saida["baseline"] = await c.call_tool(
                    "search_docs", {"domain": "techdocs", "query": "como reiniciar"}
                )
            return saida

        r = asyncio.run(roda())

        selo = _selo(r["negociado"])
        print(f"     SELO       : {json.dumps(selo, ensure_ascii=False)}")

        # ── 1 · os dois sentidos do opt-in ───────────────────────────────────────────────
        check("quem NEGOCIA a extensão recebe o selo", selo is not None)
        check(
            "quem NÃO negocia não recebe selo nenhum",
            _selo(r["mudo"]) is None,
        )
        # A asserção mais forte do arquivo: o resultado de fio de um cliente sem opt-in, no
        # servidor COM a extensão, é igual ao do servidor SEM a extensão. Não "equivalente".
        check(
            "e a resposta dele é IDÊNTICA à do servidor montado sem a extensão",
            _de_fio(r["mudo"]) == _de_fio(r["baseline"]),
        )
        check(
            "sem papel do Entra não há tool, logo não há selo "
            f"({r['sem_papel']})",
            str(r["sem_papel"]).startswith("RECUSADO"),
        )

        # ── 2 · o selo não inventa: cada campo tem fonte, e a fonte manda ────────────────
        corpo = r["negociado"].structured_content or {}
        do_corpo = [
            {"index": f["index"], "source": f["source"], "url": f["url"]}
            for f in corpo.get("sources", [])
        ]
        check(
            "as citações do selo são as MESMAS que a tool devolveu no corpo (index incluso)",
            (selo or {}).get("citations") == do_corpo == [
                {"index": l["index"], "source": l["source"], "url": l["url"]} for l in LINHAS
            ],
        )
        evento = r["evento_negociado"]
        check(
            f"o id da trilha é o hash do evento que a trilha REALMENTE gravou "
            f"({str(evento.get('hash'))[:12]}…)",
            (selo or {}).get("audit") == [
                {"scope": "access", "kind": "access", "id": evento.get("hash")}
            ],
        )
        # E o hash confere com o que a trilha devolve quando é lida — o selo não pode apontar
        # para um evento que não está lá.
        na_trilha = audit.read("access")
        check(
            "e esse hash está de fato na trilha lida de volta",
            any(e["hash"] == evento.get("hash") for e in na_trilha),
        )

        # --- mutação da fonte das citações -------------------------------------------------
        selo_sem_fonte = _selo(r["sem_fonte"]) or {}
        check(
            f"MUTAÇÃO · sem fonte, o selo sai com zero citações ({selo_sem_fonte.get('citations')!r})",
            selo_sem_fonte.get("citations") == [],
        )
        check(
            "MUTAÇÃO · e ainda assim referencia a trilha (as duas fontes são independentes)",
            bool(selo_sem_fonte.get("audit")),
        )

        # --- mutação da fonte da trilha ----------------------------------------------------
        selo_sem_trilha = _selo(r["sem_trilha"]) or {}
        check(
            "MUTAÇÃO · sem evento gravado, o selo NÃO traz referência de trilha "
            "(em vez de trazer uma inventada)",
            "audit" not in selo_sem_trilha,
        )
        check(
            "MUTAÇÃO · e as citações continuam vindo (as duas fontes são independentes)",
            len(selo_sem_trilha.get("citations") or []) == len(LINHAS),
        )

        # --- uma tool que não fundamenta nada não ganha `citations` fabricada ---------------
        # Direto na função, porque hoje só existe UMA tool e ela sempre cita: registrar uma
        # segunda tool só para este caso seria inventar superfície para testar.
        check(
            "uma resposta SEM o campo `sources` não vira `citations: []` (que mentiria "
            "dizendo que tentou citar)",
            assurance_extension._citacoes(
                ToolResult(structured_content={"qualquer": "coisa"})
            )
            is None,
        )

        # ── 3 · o selo não vaza ─────────────────────────────────────────────────────────
        selo_negado = _selo(r["negado"]) or {}
        serializado = json.dumps(selo_negado, ensure_ascii=False)
        evento_negado = r["evento_negado"]
        print(f"     NEGADO     : {serializado}")
        check(
            "chamador sem acesso: zero citações",
            selo_negado.get("citations") == [],
        )
        check(
            "e o evento que a trilha gravou NOMEIA o documento negado (o teste é honesto)",
            DOCUMENTO_RESERVADO in json.dumps(evento_negado, ensure_ascii=False),
        )
        check(
            "mas o selo NÃO carrega o nome do documento",
            DOCUMENTO_RESERVADO not in serializado,
        )
        check(
            "nem o `detail`, o `summary` ou o ator do evento",
            all(
                pedaco not in serializado
                for pedaco in ("detail", "summary", "documents", "com.papel@exemplo.invalid")
            ),
        )
        check(
            "o que sobra do evento é só escopo, tipo e id",
            all(set(e) == {"scope", "kind", "id"} for e in selo_negado.get("audit", [])),
        )
    finally:
        (
            mcp_main.build_auth,
            tools_knowledge.retrieve,
            settings.entra_tenant_id,
            settings.entra_api_client_id,
            settings.mcp_public_base_url,
        ) = original
        shared_auth._current_user.set(None)
        logging.disable(logging.NOTSET)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o selo é negociado, copia o que já existia, e não conta nada que o chamador não possa ver.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
