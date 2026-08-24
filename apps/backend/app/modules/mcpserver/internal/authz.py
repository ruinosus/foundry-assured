"""Autorização por App Role, no vocabulário do FastMCP.

PONTE TEMPORÁRIA, e marcada como tal. O `require_roles(..., extract=...)` do FastMCP 4.x faz
exatamente isto em uma linha, com o extractor do Entra (`lambda c: c["roles"]`) documentado.
Ele NÃO existe no 3.4.7 — verificado por introspecção do pacote instalado, não suposto. Quando
o 4 entrar, este arquivo é deletado, não refatorado.

A regra em si mora em `has_any_role`, uma função pura sobre o dicionário de claims: é o
contrato de negócio ("quais claims concedem"), e ele não deve mudar quando a biblioteca
renomear um objeto de contexto.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from app.shared.settings import settings


def has_any_role(claims: dict[str, Any], roles: tuple[str, ...]) -> bool:
    """True se `claims["roles"]` contém QUALQUER um de `roles`.

    Admin não é implicitamente concedido — quem quiser que Admin passe, lista Admin. É a mesma
    doutrina de `app.shared.auth.require_role`, e a divergência entre as duas seria pior que a
    duplicação.
    """
    concedidos = claims.get("roles")
    if not isinstance(concedidos, list):  # claim ausente ou de tipo inesperado
        return False
    return bool(set(roles) & set(concedidos))


def role_check(*roles: str) -> Callable[[Any], bool]:
    """Adaptador para `@mcp.tool(auth=...)`: recebe o contexto do FastMCP, devolve bool.

    Com a auth desligada devolve sempre True — o mesmo degradar-aberto de
    `app.shared.auth.has_role`, para que o dev local não precise de um Entra.
    """

    def check(ctx: Any) -> bool:
        if not settings.auth_enabled:
            return True
        token = getattr(ctx, "token", None)
        if token is None:
            return False
        return has_any_role(getattr(token, "claims", {}) or {}, roles)

    return check
