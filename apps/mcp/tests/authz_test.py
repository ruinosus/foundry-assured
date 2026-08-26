"""O papel do Entra decide quais tools o chamador enxerga.

O contrato de negócio é ANY-OF: quem tem Reader, OU Author, OU Approver, OU Admin pode buscar.
É a mesma doutrina de `app.shared.auth.require_role`, e a divergência entre as duas seria pior
que a duplicação — as duas superfícies discordariam sobre quem pode ler o quê.

A PRIMEIRA METADE DESTE TESTE É SOBRE A BIBLIOTECA, DE PROPÓSITO. O plano desta fase era trocar
a ponte escrita à mão do monolito (`authz.py`) por `require_roles(...)` de biblioteca, uma linha.
Medido no pacote instalado, `require_roles` do FastMCP 4.0.0b3 é **AND** ("All are required (AND
logic)"), não OR — `require_roles("Reader","Author","Approver","Admin", …)` exigiria os quatro
papéis do mesmo chamador e a tool sumiria do `tools/list` para todo mundo, sem erro nenhum
(tool negada por `auth=` é FILTRADA, não recusada — `fastmcp/server/server.py:879`).

Por isso as duas verificações que abrem: elas travam a semântica da BIBLIOTECA sobre a qual o
nosso `require_any_role` se apoia. Se um FastMCP futuro trocar AND por OR, o composto continua
correto — mas estas duas ficam vermelhas e alguém revisita a decisão em vez de herdar.

    uv run python -m tests.authz_test
"""

from __future__ import annotations

import sys

from fastmcp.server.auth import require_roles

from app.shared.settings import settings
from mcp_app.auth import _papeis_do_entra, require_any_role

#: Sentinela: "não há token nenhum", que é diferente de "há token sem o claim `roles`".
SEM_TOKEN = object()


class _Token:
    def __init__(self, claims):
        self.claims = claims


class _Ctx:
    """O que um `AuthCheck` lê do `AuthContext`: `.token`, e dele `.claims`."""

    def __init__(self, claims):
        self.token = None if claims is SEM_TOKEN else _Token(claims)


def com_papeis(roles) -> _Ctx:
    return _Ctx({"roles": roles})


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    original = (settings.entra_tenant_id, settings.entra_api_client_id)
    try:
        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"

        # ── a semântica da biblioteca, travada ───────────────────────────────────────────
        dois = require_roles("Approver", "Admin", extract=_papeis_do_entra)
        check(
            "require_roles do FastMCP é AND: ter só um dos dois NÃO concede",
            not dois(com_papeis(["Approver"])),
        )
        check(
            "require_roles do FastMCP é AND: ter os dois concede",
            dois(com_papeis(["Approver", "Admin"])),
        )

        # ── o contrato de negócio: ANY-OF ────────────────────────────────────────────────
        gate = require_any_role("Approver", "Admin")
        check("papel presente concede", gate(com_papeis(["Approver"])))
        check("qualquer um da lista concede", gate(com_papeis(["Admin"])))
        check("papel errado nega", not gate(com_papeis(["Reader"])))
        check("token sem o claim de papel nega", not gate(_Ctx({})))
        check("sem token nega", not gate(_Ctx(SEM_TOKEN)))
        # Um provider que guarda papel único como string nua é tratado pela biblioteca (o
        # docstring de `require_roles` documenta): "Approver" vale como o papel "Approver", e
        # não como as letras dele.
        check("claim escalar é o papel que ela diz ser, não os caracteres", gate(com_papeis("Approver")))
        check("claim escalar errada nega", not gate(com_papeis("Reader")))
        # Claim de tipo inesperado nega em vez de explodir — `_RequireRoles` captura `TypeError`.
        check("claim de tipo errado nega em vez de explodir", not gate(com_papeis(7)))

        # ── DIVERGÊNCIA EM RELAÇÃO AO MONOLITO, documentada — não corrigida ────────────────
        # `app/modules/mcpserver/internal/authz.py:29` faz `isinstance(concedidos, list)` e
        # NEGA os dois casos acima: string nua ("Approver") e tupla (("Approver",)) — só lista
        # concede lá. Este app CONCEDE os dois, porque `_RequireRoles.__call__` (biblioteca)
        # faz `set(extracted)` sobre qualquer coisa que não seja `str` — uma tupla vira
        # `{"Approver"}` igual a uma lista.
        #
        # O monolito é o MAIS ESTRITO dos dois — e é o comportamento correto por acidente, não
        # por design: a checagem existe para negar claim malformado, não para aceitar só um
        # tipo específico de coleção. A divergência NÃO É ALCANÇÁVEL hoje: o Entra sempre emite
        # `roles` como array JSON (nunca string nem tupla — tupla nem existe em JSON), então
        # nenhum token real do Entra cai neste ramo. Registrado aqui para não parecer
        # comportamento não-testado; a correção (se algum dia importar) é decisão de produto,
        # não deste PR — trocar de biblioteca não é.
        check(
            "DIVERGÊNCIA: tupla de papel único também concede aqui (o monolito negaria)",
            gate(com_papeis(("Approver",))),
        )

        # ── os quatro papéis reais da tool ───────────────────────────────────────────────
        tool_gate = require_any_role("Reader", "Author", "Approver", "Admin")
        for papel in ("Reader", "Author", "Approver", "Admin"):
            check(f"{papel} sozinho abre a tool search_docs", tool_gate(com_papeis([papel])))
        check("papel desconhecido não abre", not tool_gate(com_papeis(["Auditor"])))

        # ── auth desligada: dev local ────────────────────────────────────────────────────
        settings.entra_tenant_id = ""
        settings.entra_api_client_id = ""
        aberto = require_any_role("Approver")
        check("auth desligada: passa (dev local, igual ao resto do backend)", aberto(_Ctx(SEM_TOKEN)))
    finally:
        settings.entra_tenant_id, settings.entra_api_client_id = original

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ papel do Entra decide; sem papel, a tool não existe para o chamador.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
