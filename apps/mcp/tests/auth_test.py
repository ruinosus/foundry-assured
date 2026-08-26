"""O MCP é um Resource Server, não um authorization server.

A escolha é de segurança, não de estilo: o OAuth proxy do FastMCP exigiria `client_secret` e
faria o servidor emitir tokens — uma segunda malha de identidade convivendo com a do Entra que
já vale para o resto do backend. O verifier só CONFERE o token que o cliente já trouxe.

Este teste trava as coisas que, se mudarem em silêncio, quebram essa escolha: o provider some
quando a auth está desligada, o issuer é o do NOSSO tenant, e o escopo exigido é o mesmo
`access_as_user` que o `fastapi-azure-auth` já cobra.

O QUE MUDOU EM RELAÇÃO AO TESTE DO MONOLITO, e por quê. Lá a última verificação era
`provider.resource_base_url == BASE + "/mcp"`: no monolito o MCP servia em `"/"` dentro de um
sub-app montado em `/mcp`, então o provider via `mcp_path="/"` e derivava o recurso como a RAIZ
do host — `resource_base_url` existia só para corrigir isso. Aqui não há mount: o caminho viaja
em `http_app(path="/mcp/")` e o provider já deriva `base_url + "/mcp/"` sozinho. Definir
`resource_base_url` agora produziria `https://host/mcp/mcp/`.

Então a verificação equivalente mudou de forma, não de conteúdo: em vez de conferir o campo que
corrigia o recurso, ela confere o RESULTADO — o caminho da rota de metadata que o provider
gera, que é onde o recurso aparece escopado ao endpoint. O fim-a-fim (o 401 anunciando uma URL
que responde 200) é `unauthenticated_test`.

    uv run python -m tests.auth_test
"""

from __future__ import annotations

import sys

from app.shared.settings import settings
from mcp_app.auth import MCP_PATH, build_auth

BASE = "https://exemplo.invalid"


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    original = (settings.entra_tenant_id, settings.entra_api_client_id)
    try:
        settings.entra_tenant_id = ""
        settings.entra_api_client_id = ""
        check("auth desligada → sem provider", build_auth(BASE) is None)

        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"
        provider = build_auth(BASE)
        check("auth ligada → provider construído", provider is not None)

        servers = [str(u) for u in provider.authorization_servers]
        check(
            "issuer é o do nosso tenant, v2.0",
            servers == ["https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0"],
        )
        check(
            "escopo exigido é o mesmo do resto do backend",
            provider.token_verifier.required_scopes == ["access_as_user"],
        )
        check(
            "issuer do verifier é o tenant_id, não o client_id",
            provider.token_verifier.issuer
            == "https://login.microsoftonline.com/11111111-1111-1111-1111-111111111111/v2.0",
        )
        check(
            "audience do verifier é o client_id, não o tenant_id",
            provider.token_verifier.audience
            == ["22222222-2222-2222-2222-222222222222", "api://22222222-2222-2222-2222-222222222222"],
        )

        # O recurso anunciado é o ENDPOINT, não a raiz do backend: é o que o cliente compara com
        # o servidor que está chamando. Sem mount, quem carrega essa verdade é o `mcp_path`.
        caminhos = [r.path for r in provider.get_well_known_routes(mcp_path=MCP_PATH)]
        print(f"     rotas .well-known: {caminhos}")
        check(
            "a metadata é escopada ao endpoint MCP, não à raiz",
            caminhos == [f"/.well-known/oauth-protected-resource{MCP_PATH}"],
        )
        check(
            "e o provider não redefine o recurso por conta própria (sem mount, não há o que corrigir)",
            provider.resource_base_url is None,
        )
    finally:
        settings.entra_tenant_id, settings.entra_api_client_id = original

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o MCP valida o token do Entra sem emitir nenhum.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
