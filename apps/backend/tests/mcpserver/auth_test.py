"""O MCP é um Resource Server, não um authorization server.

A escolha é de segurança, não de estilo: o OAuth proxy do FastMCP exigiria `client_secret` e
faria o servidor emitir tokens — uma segunda malha de identidade convivendo com a do Entra que
já vale para o resto do backend. O verifier só CONFERE o token que o cliente já trouxe.

Este teste trava as três coisas que, se mudarem em silêncio, quebram essa escolha:
o provider some quando a auth está desligada, o issuer é o do NOSSO tenant, e o escopo exigido
é o mesmo `access_as_user` que o `fastapi-azure-auth` já cobra.

    uv run python -m tests.mcpserver.auth_test
"""

from __future__ import annotations

import sys

from app.modules.mcpserver.internal.auth import build_auth
from app.modules.mcpserver.internal.server import MOUNT_PATH
from app.shared.settings import settings

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
        check("auth desligada → sem provider", build_auth(BASE, MOUNT_PATH) is None)

        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"
        provider = build_auth(BASE, MOUNT_PATH)
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
        # o servidor que está chamando, e é de onde sai a URL da metadata no desafio 401.
        check(
            "o recurso protegido é o endpoint montado, não a raiz",
            str(provider.resource_base_url).rstrip("/") == f"{BASE}{MOUNT_PATH}",
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
