"""Auth do MCP: Resource Server sobre o Entra, sem segredo — e autorização por App Role.

POR QUE NÃO O OAUTH PROXY. O `AzureProvider` do FastMCP exige `client_secret` e transforma o
servidor num authorization server intermediário. Isso seria uma SEGUNDA malha de identidade ao
lado da que `app/shared/auth.py` já opera — duas respostas para "quem é o chamador". O
`AzureJWTVerifier` não pede segredo nenhum: ele valida o mesmo token que o `fastapi-azure-auth`
já valida, contra a mesma app registration. Também é o que mantém a ADR-005 de pé: um app que
não recebe segredo não tem segredo para guardar.

Assinaturas lidas do pacote instalado (fastmcp 4.0.0b3), não da documentação (regra 1). O
`AzureJWTVerifier.__init__` e o `RemoteAuthProvider.__init__` são IDÊNTICOS aos do 3.4.7 —
conferido por `inspect.signature` antes de portar, e é por isso que este arquivo é uma cópia e
não uma reescrita.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import Any

from fastmcp.server.auth import AuthCheck, RemoteAuthProvider, require_roles
from fastmcp.server.auth.providers.azure import AzureJWTVerifier

from app.shared.settings import ENTRA_API_SCOPE_NAME, settings

#: O caminho público do endpoint MCP. Igual ao do monolito de propósito: na Fase 0c este app
#: assume a URL que o `/mcp` do monolito serve hoje, e um cliente já configurado não deve
#: precisar reconfigurar nada.
#:
#: Aqui ele viaja por `mcp.http_app(path=...)`, não por um `app.mount()` de fora — este app É a
#: raiz. É a diferença que apaga o conserto mais delicado da versão do monolito: lá, a rota
#: `.well-known` que o FastMCP registra caía DENTRO do sub-app (`/mcp/.well-known/…`) enquanto o
#: desafio 401 anunciava a URL a partir da raiz do host, e o `main.py` precisava reerguer as
#: rotas na raiz à mão. Sem mount, `http_app` já registra tudo na mesma lista de rotas da raiz
#: (`fastmcp/server/http.py:604`), e a placa do 401 aponta para onde a rota existe.
MCP_PATH = "/mcp/"


def build_auth(base_url: str) -> RemoteAuthProvider | None:
    """O provider de auth do MCP, ou None quando a auth está desligada (dev local).

    `None` é o mesmo comportamento que o resto do backend tem sem Entra configurado — ver
    `settings.auth_enabled`. Não inventar exceção aqui: um MCP que exige token onde o app não
    exige tornaria o dev local diferente da produção justamente na parte que precisa ser igual.

    SEM `resource_base_url`, e isto MUDOU em relação ao monolito. Lá ele existia para corrigir
    o recurso anunciado: o provider deriva o recurso de `base_url + mcp_path`
    (`AuthProvider._get_resource_url`), e com o MCP servindo em `"/"` dentro de um sub-app
    montado em `/mcp`, o `mcp_path` que ele via era `"/"` — o recurso saía `https://host/`
    enquanto o endpoint era `https://host/mcp/`. Aqui o `mcp_path` É `/mcp/`, então
    `base_url + MCP_PATH` já é a verdade. Passar `resource_base_url=base_url + "/mcp"` agora
    produziria `https://host/mcp/mcp/` — a mesma classe de defeito, ao contrário.
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
        resource_name="Foundry Assured MCP",
    )


def _papeis_do_entra(claims: dict[str, Any]) -> Iterable[str]:
    """Onde o Entra guarda os App Roles do chamador: o claim `roles`.

    É exatamente o extractor que o docstring de `require_roles` documenta para o Entra. Fica no
    call site, e não dentro da biblioteca, porque cada IdP guarda em lugar diferente
    (`realm_access.roles` no Keycloak, `cognito:groups` no Cognito).
    """
    return claims.get("roles") or []


def require_any_role(*roles: str) -> AuthCheck:
    """Concede se o chamador tem QUALQUER um de `roles`. Sem papel, a tool não existe para ele.

    POR QUE NÃO É UM `require_roles(...)` SÓ, que era o plano. `require_roles` do FastMCP
    4.0.0b3 é **AND**, não OR — lido na fonte do pacote instalado, não na intenção da spec:

        class _RequireRoles:
            def __call__(self, ctx): ... return self.required_roles.issubset(granted)

    e o próprio docstring diz "All are required (AND logic)". Escrever
    `require_roles("Reader", "Author", "Approver", "Admin", extract=...)` exigiria que o
    chamador tivesse os QUATRO papéis ao mesmo tempo — ninguém tem — e a tool sumiria do
    `tools/list` para todo mundo. Seria uma regressão de comportamento em fase cujo critério é
    paridade, e do tipo pior: falha silenciosa, porque uma tool negada por `auth=` é FILTRADA,
    não recusada com erro (`server.py:879`).

    Não existe `require_any_role` na biblioteca (`fastmcp.server.auth` exporta apenas
    `require_roles`, `require_scopes` e `restrict_tag`), e compor checks numa lista também é AND
    (`run_auth_checks`). Então o OR é nosso — mas SÓ o OR: cada parcela continua sendo um
    `require_roles` de biblioteca, que é quem trata token ausente, claim ausente e o caso do
    provider que guarda um papel único como string nua. Nada disso é reimplementado aqui.

    Com a auth desligada devolve sempre True — o mesmo degradar-aberto de
    `app.shared.auth.has_role`, para que o dev local não precise de um Entra. É necessário: o
    FastMCP roda os checks de `auth=` mesmo sem provider nenhum (transporte não-stdio →
    `ctx.token is None` → negado), então sem esta guarda o app sem Entra não serviria a tool
    para ninguém.
    """
    checks = [require_roles(role, extract=_papeis_do_entra) for role in roles]

    def concede(ctx) -> bool:
        if not settings.auth_enabled:
            return True
        return any(check(ctx) for check in checks)

    return concede
