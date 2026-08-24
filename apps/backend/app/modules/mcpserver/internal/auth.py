"""Auth do MCP: Resource Server sobre o Entra, sem segredo.

POR QUE NÃO O OAUTH PROXY. O `AzureProvider` do FastMCP exige `client_secret` e transforma o
servidor num authorization server intermediário. Isso seria uma SEGUNDA malha de identidade ao
lado da que `app/shared/auth.py` já opera — duas respostas para "quem é o chamador". O
`AzureJWTVerifier` não pede segredo nenhum: ele valida o mesmo token que o
`fastapi-azure-auth` já valida, contra a mesma app registration.

Assinaturas lidas do pacote instalado (fastmcp 3.4.7), não da documentação (regra 1).
"""

from __future__ import annotations

from fastmcp.server.auth import RemoteAuthProvider
from fastmcp.server.auth.providers.azure import AzureJWTVerifier

from app.shared.settings import settings

#: O mesmo escopo que `settings.entra_api_scope` compõe (`api://<client_id>/access_as_user`).
#: O verifier recebe só o nome, porque ele prefixa com o `identifier_uri` sozinho.
SCOPE = "access_as_user"


def build_auth(base_url: str) -> RemoteAuthProvider | None:
    """O provider de auth do MCP, ou None quando a auth está desligada (dev local).

    `None` é o mesmo comportamento que o resto do backend tem sem Entra configurado — ver
    `settings.auth_enabled`. Não inventar exceção aqui: um MCP que exige token onde o app não
    exige tornaria o dev local diferente da produção justamente na parte que precisa ser igual.
    """
    if not settings.auth_enabled:
        return None

    verifier = AzureJWTVerifier(
        client_id=settings.entra_api_client_id,
        tenant_id=settings.entra_tenant_id,
        required_scopes=[SCOPE],
    )
    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[
            f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
        ],
        base_url=base_url,
        resource_name="Foundry Assured MCP",
    )
