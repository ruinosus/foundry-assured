"""O papel do Entra decide quais tools o chamador enxerga.

Por que a lógica é uma função PURA sobre `claims` e não um check acoplado ao `AuthContext` do
FastMCP: o contrato que precisa ser travado é "quais claims concedem acesso", e ele não deve
mudar quando a biblioteca renomear um objeto. O adaptador é a casca fina em volta.

No 4.x isto vira `require_roles("Approver", extract=lambda c: c["roles"])`, uma linha de
biblioteca. Esta ponte existe porque `require_roles` NÃO existe no 3.4.7 (verificado por
introspecção) — e some quando o 4 entrar.

    uv run python -m tests.mcpserver.authz_test
"""

from __future__ import annotations

import sys

from app.modules.mcpserver.internal.authz import has_any_role, role_check
from app.shared.settings import settings


class _Token:
    def __init__(self, roles):
        self.claims = {"roles": roles} if roles is not None else {}


class _Ctx:
    def __init__(self, roles):
        self.token = _Token(roles) if roles is not None else None


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    check("papel presente concede", has_any_role({"roles": ["Approver"]}, ("Approver", "Admin")))
    check("qualquer um da lista concede", has_any_role({"roles": ["Admin"]}, ("Approver", "Admin")))
    check("papel errado nega", not has_any_role({"roles": ["Reader"]}, ("Approver", "Admin")))
    check("sem claim de papel nega", not has_any_role({}, ("Approver",)))
    check("claim de tipo errado nega em vez de explodir", not has_any_role({"roles": "Approver"}, ("Approver",)))

    original = (settings.entra_tenant_id, settings.entra_api_client_id)
    try:
        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"
        gate = role_check("Approver", "Admin")
        check("adaptador: Approver passa", gate(_Ctx(["Approver"])))
        check("adaptador: Reader não passa", not gate(_Ctx(["Reader"])))
        check("adaptador: sem token não passa", not gate(_Ctx(None)))

        settings.entra_tenant_id = ""
        settings.entra_api_client_id = ""
        aberto = role_check("Approver")
        check("auth desligada: passa (dev local, igual ao resto do backend)", aberto(_Ctx(None)))
    finally:
        settings.entra_tenant_id, settings.entra_api_client_id = original

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ papel do Entra decide; sem papel, a tool não existe para o chamador.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
