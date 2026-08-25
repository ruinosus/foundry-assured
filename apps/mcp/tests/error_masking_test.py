"""Erro que sai pelo MCP não conta como o backend é feito por dentro.

O QUE ESTE TESTE IMPEDE. O default do fastmcp é `mask_error_details=False`: toda exceção que a
tool levanta volta ao chamador com o texto original. A tool `search_docs` chama o Azure Search,
e um 404 dele carrega, na mensagem, o endpoint do serviço, o nome do índice e a api-version —
inventário de infraestrutura entregue a quem só pediu uma busca. O caminho web nunca fez isso
(erro inesperado vira 500 genérico), e a superfície nova não pode ser onde a regra afrouxa.

A CONTRAPARTIDA IMPORTA TANTO QUANTO. Mascarar tudo tornaria a tool inutilizável: quem chama
precisa saber que passou um domínio inválido, ou que esqueceu o token. Por isso esses dois
casos são levantados como `ToolError`, que o fastmcp deixa passar INTEIRO — e é isso que a
segunda metade do teste trava. Sem ela, "mascarar" viraria "emudecer" no primeiro refactor.

Roda offline e sem auth: com `ENTRA_*` em branco não há provider, e o cliente em memória do
próprio fastmcp fala com o servidor sem rede.

PORTADO DO MONOLITO com uma mudança e uma só: `build_mcp` vive em `mcp_app/main.py` e não
registra a tool — quem registra é `main.build_app`, então o teste chama `register` ele mesmo.
Nenhuma asserção mudou.

    uv run python -m tests.error_masking_test
"""

from __future__ import annotations

import asyncio
import sys

from fastmcp import Client

from app.shared.settings import settings
from mcp_app import tools_knowledge
from mcp_app.auth import MCP_PATH
from mcp_app.main import build_mcp

#: Uma mensagem de erro com a cara da que o Azure Search devolve — os três dados que não podem
#: vazar estão dentro dela.
SEGREDO_DE_INFRA = (
    "(ResourceNotFound) https://busca-interna.search.windows.net/indexes/"
    "techdocs-si-idx/docs/search?api-version=2026-05-01-preview returned 404"
)


async def _chamar(mcp, **argumentos) -> str:
    """Chama `search_docs` pelo cliente em memória e devolve o texto do erro."""
    async with Client(mcp) as client:
        try:
            await client.call_tool("search_docs", argumentos)
        except Exception as exc:  # noqa: BLE001 — é o texto do erro que está sob teste
            return str(exc)
    return ""


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    async def retrieve_que_explode(query, user, domain, *, top=8):
        raise RuntimeError(SEGREDO_DE_INFRA)

    original_retrieve = tools_knowledge.retrieve
    original_lookup = tools_knowledge._domain_lookup
    original_grounded = tools_knowledge._grounded_domains
    original_entra = (settings.entra_tenant_id, settings.entra_api_client_id)
    try:
        settings.entra_tenant_id = ""  # auth desligada: o cliente em memória entra sem token
        settings.entra_api_client_id = ""
        tools_knowledge.retrieve = retrieve_que_explode
        tools_knowledge.set_domain_registry(
            lambda domain_id: f"spec:{domain_id}", ("techdocs", "selfwiki")
        )
        # `build_mcp` monta o servidor; registrar a tool é passo separado neste app
        # (`main.build_app` faz os dois). Aqui só a tool importa — nada de HTTP.
        mcp = build_mcp(auth=None)
        tools_knowledge.register(mcp)

        texto = asyncio.run(_chamar(mcp, domain="techdocs", query="qualquer"))
        print(f"     erro devolvido: {texto}")
        check("a falha inesperada vira erro para o chamador", bool(texto))
        for vazamento in ("search.windows.net", "techdocs-si-idx", "api-version"):
            check(f"não vaza {vazamento!r} para o cliente MCP", vazamento not in texto)

        # O erro que o chamador PRECISA ler continua inteiro.
        recusa = asyncio.run(_chamar(mcp, domain="helpdesk", query="qualquer"))
        print(f"     recusa devolvida: {recusa}")
        check(
            "domínio sem base ainda diz o que fazer (ToolError não é mascarado)",
            "techdocs" in recusa and "selfwiki" in recusa,
        )
    finally:
        tools_knowledge.retrieve = original_retrieve
        tools_knowledge._domain_lookup = original_lookup
        tools_knowledge._grounded_domains = original_grounded
        settings.entra_tenant_id, settings.entra_api_client_id = original_entra

    print(f"\n  (superfície sob teste: {MCP_PATH})")
    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o chamador recebe o que precisa e nada do que não é dele.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
