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

from app.shared.settings import ENTRA_API_SCOPE_NAME, settings


def build_auth(base_url: str, mount_path: str) -> RemoteAuthProvider | None:
    """O provider de auth do MCP, ou None quando a auth está desligada (dev local).

    `mount_path` é o prefixo onde o composition root monta o sub-app (`/mcp`). Ele chega por
    parâmetro, e não por import, porque quem o declara é `server.py` — que já importa este
    módulo; importar de volta fecharia ciclo.

    `None` é o mesmo comportamento que o resto do backend tem sem Entra configurado — ver
    `settings.auth_enabled`. Não inventar exceção aqui: um MCP que exige token onde o app não
    exige tornaria o dev local diferente da produção justamente na parte que precisa ser igual.
    """
    if not settings.auth_enabled:
        return None

    verifier = AzureJWTVerifier(
        client_id=settings.entra_api_client_id,
        tenant_id=settings.entra_tenant_id,
        required_scopes=[ENTRA_API_SCOPE_NAME],
    )
    return RemoteAuthProvider(
        token_verifier=verifier,
        authorization_servers=[
            f"https://login.microsoftonline.com/{settings.entra_tenant_id}/v2.0"
        ],
        base_url=base_url,
        # O RECURSO ANUNCIADO É O ENDPOINT DE VERDADE, não a raiz do backend. Sem isto o
        # provider deriva o `resource` de `base_url` e publica `https://host/` — mas o MCP
        # responde em `https://host/mcp/`, porque o `main.py` o monta em prefixo. Um cliente que
        # confere o `resource` da metadata contra o servidor com que fala veria os dois
        # discordando. `resource_base_url` existe no `RemoteAuthProvider` do fastmcp 3.4.7
        # exatamente para este caso (lido da fonte do pacote instalado, regra 1) e move JUNTO a
        # URL da metadata e a do desafio 401 — as duas derivam dele.
        resource_base_url=f"{base_url.rstrip('/')}{mount_path}",
        resource_name="Foundry Assured MCP",
    )
