"""No modo `shared`, o MCP resolve o tenant do chamador e cobra o entitlement.

DUAS COISAS SEPARADAS, e a segunda é a que a revisão final apontou como perigosa. Resolver o
tenant sem cobrar o entitlement (ADR-010) serve domínio NÃO LICENCIADO — e é o conserto
"óbvio" que alguém faria olhando só o sintoma (a busca falhando por falta de tenant).

A regra de entitlement é UMA (`tenancy.domain_enabled`) e vale para as duas superfícies. Este
teste prova que o caminho MCP a usa; `require_domain` continua provando o lado do FastAPI.

PORTADO DO MONOLITO (`apps/backend/tests/mcpserver/shared_tenancy_test.py`) sem uma única
mudança de asserção — só o caminho do módulo mudou (`app.modules.mcpserver.internal.
tools_knowledge` → `mcp_app.tools_knowledge`). É de propósito: esta fase tem paridade como
critério. Este teste é a única cobertura de tenancy/entitlement do modo `shared` no app novo —
o gate do monolito morre com o `mcpserver/` dele na Fase 0c, e sem este porte o modo `shared`
deste app ficaria sem gate nenhum.

    uv run python -m tests.shared_tenancy_test
"""

from __future__ import annotations

import asyncio
import sys

from app.modules.tenancy.public import set_current_tenant
from app.shared.settings import settings
from mcp_app import tools_knowledge


class _Registro:
    def __init__(self, tid, enabled, status="active"):
        self.tid = tid
        self.enabled_domains = enabled
        self.status = status


class _Token:
    def __init__(self, tid):
        self.token = "token-do-chamador"
        self.claims = {"oid": "o-1", "roles": ["Reader"], "tid": tid}


def main() -> int:
    falhas: list[str] = []
    visto: dict = {}

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    async def falso_retrieve(query, user, domain, *, top=8):
        visto["tid_no_retrieve"] = getattr(user, "tid", None)
        return [{"index": 1, "source": "d.md", "url": "https://x/1", "snippet": "s"}]

    loja = {"t-ok": _Registro("t-ok", ("techdocs",)),
            "t-sem": _Registro("t-sem", ("selfwiki",)),
            "t-off": _Registro("t-off", ("techdocs",), status="suspended")}

    originais = (tools_knowledge.retrieve, tools_knowledge.get_access_token,
                 settings.deployment_mode, settings.entra_tenant_id,
                 settings.entra_api_client_id)
    # `search_docs` recusa domínio antes de qualquer coisa se a composition root não empurrou o
    # registry (pré-requisito de todo teste deste módulo — mesmo setup do
    # identity_passthrough_test, que não é o que esta suíte prova).
    registry_original = (tools_knowledge._domain_lookup, tools_knowledge._grounded_domains)
    try:
        tools_knowledge.retrieve = falso_retrieve
        tools_knowledge.set_domain_registry(lambda d: f"spec:{d}", ("techdocs", "selfwiki"))
        settings.deployment_mode = "shared"
        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"
        tools_knowledge.set_tenant_store(lambda tid: loja.get(tid))

        tools_knowledge.get_access_token = lambda: _Token("t-ok")
        r = asyncio.run(tools_knowledge.search_docs("techdocs", "q"))
        check("tenant licenciado passa", bool(r.get("sources")))
        check("o tid do chamador chegou ao retrieve", visto.get("tid_no_retrieve") == "t-ok")

        tools_knowledge.get_access_token = lambda: _Token("t-sem")
        try:
            asyncio.run(tools_knowledge.search_docs("techdocs", "q"))
            check("domínio NÃO licenciado é recusado", False)
        except Exception as exc:  # noqa: BLE001 — é o texto do erro que está sob teste
            # Mensagem EXATA, não substring: "tenant não habilitado" também contém
            # "não habilitado" — uma comparação frouxa passaria mesmo se o mutante que a
            # revisão rodou (apagar `domain_enabled` do caminho MCP) removesse este gate.
            check(
                "domínio NÃO licenciado é recusado",
                str(exc) == "domínio não habilitado para o tenant: techdocs",
            )

        tools_knowledge.get_access_token = lambda: _Token("t-off")
        try:
            asyncio.run(tools_knowledge.search_docs("techdocs", "q"))
            check("tenant suspenso é recusado", False)
        except Exception as exc:  # noqa: BLE001 — é o texto do erro que está sob teste
            check("tenant suspenso é recusado", str(exc) == "tenant não habilitado")

        tools_knowledge.get_access_token = lambda: _Token("t-inexistente")
        try:
            asyncio.run(tools_knowledge.search_docs("techdocs", "q"))
            check("tenant desconhecido é recusado", False)
        except Exception as exc:  # noqa: BLE001 — é o texto do erro que está sob teste
            check("tenant desconhecido é recusado", str(exc) == "tenant não habilitado")

        # Seam quebrado (setup, não entitlement): se a composition root deixar de empurrar a
        # loja, o erro é OUTRO ("tenant store não registrado") — precisa continuar distinto do
        # "tenant não habilitado" acima, senão as três checagens de recusa passariam pelo
        # motivo errado quando `set_tenant_store` parar de ser chamado.
        tools_knowledge.set_tenant_store(None)
        tools_knowledge.get_access_token = lambda: _Token("t-ok")
        try:
            asyncio.run(tools_knowledge.search_docs("techdocs", "q"))
            check("loja de tenant não registrada é recusada, com o motivo certo", False)
        except Exception as exc:  # noqa: BLE001 — é o texto do erro que está sob teste
            check(
                "loja de tenant não registrada é recusada, com o motivo certo",
                str(exc) == "tenant store não registrado",
            )
        tools_knowledge.set_tenant_store(lambda tid: loja.get(tid))

        # A composition root empurra `tenant_store().get` — o MÉTODO vinculado, não a loja em
        # si (`mcp_app/main.py::wire_registry`). A loja tem `.get` mas não é chamável: se
        # alguém passasse o objeto cru por engano, o boot ficaria verde e só a primeira chamada
        # da tool quebraria.
        tools_knowledge.set_tenant_store(loja)  # type: ignore[arg-type] — propositalmente errado
        try:
            asyncio.run(tools_knowledge.search_docs("techdocs", "q"))
            check("loja crua (não a função `.get`) quebra na primeira chamada", False)
        except TypeError:
            check("loja crua (não a função `.get`) quebra na primeira chamada", True)
        except Exception:  # noqa: BLE001 — só o TypeError de "não é chamável" prova o ponto
            check("loja crua (não a função `.get`) quebra na primeira chamada", False)
        tools_knowledge.set_tenant_store(lambda tid: loja.get(tid))

        settings.deployment_mode = "self_hosted"
        tools_knowledge.get_access_token = lambda: _Token(None)
        set_current_tenant(None)
        r = asyncio.run(tools_knowledge.search_docs("techdocs", "q"))
        check("fora do shared, nada de tenant é exigido (self_hosted)", bool(r.get("sources")))

        settings.deployment_mode = "dedicated"
        tools_knowledge.get_access_token = lambda: _Token(None)
        set_current_tenant(None)
        r = asyncio.run(tools_knowledge.search_docs("techdocs", "q"))
        check("fora do shared, nada de tenant é exigido (dedicated)", bool(r.get("sources")))
    finally:
        (tools_knowledge.retrieve, tools_knowledge.get_access_token,
         settings.deployment_mode, settings.entra_tenant_id,
         settings.entra_api_client_id) = originais
        tools_knowledge._domain_lookup, tools_knowledge._grounded_domains = registry_original
        tools_knowledge.set_tenant_store(None)
        set_current_tenant(None)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o MCP no shared resolve tenant E cobra entitlement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
