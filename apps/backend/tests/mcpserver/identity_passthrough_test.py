"""O token do CHAMADOR chega ao retrieve — é isso que faz o trim de ACL ser dele, e não nosso.

Este é o teste que impede a falha mais cara possível nesta camada: a tool funcionar, devolver
resultado bonito, e estar buscando como a IDENTIDADE DA APLICAÇÃO. Nesse caso o índice
continua carimbado, o `retrieve` continua respondendo, e o usuário recebe documento que não
pode ver — sem erro, sem log, sem sintoma.

`retrieve` usa do `user` exatamente um atributo: `.access_token` (retrieval.py:144, que o
passa como `user_assertion` do OnBehalfOfCredential). Este teste trava essa passagem.

O gate de vazamento de verdade (`eval/access_control_test`) precisa de nuvem e de identidades
de teste; ele roda em `security-gates.yml`. Este aqui é o que dá para exigir em todo push.

    uv run python -m tests.mcpserver.identity_passthrough_test
"""

from __future__ import annotations

import asyncio
import sys

from app.modules.mcpserver.internal import tools_knowledge


class _Token:
    def __init__(self, raw: str) -> None:
        self.token = raw
        self.claims = {"roles": ["Reader"]}


def main() -> int:
    falhas: list[str] = []
    visto: dict = {}

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    async def falso_retrieve(query, user, domain, *, top=8):
        visto["query"] = query
        visto["assertion"] = getattr(user, "access_token", None)
        visto["domain"] = domain
        return [{"index": 1, "source": "runbook.md", "url": "https://x/1", "snippet": "trecho"}]

    original_retrieve = tools_knowledge.retrieve
    original_token = tools_knowledge.get_access_token
    original_lookup = tools_knowledge._domain_lookup
    try:
        tools_knowledge.retrieve = falso_retrieve
        tools_knowledge.get_access_token = lambda: _Token("token-do-chamador")
        tools_knowledge.set_domain_lookup(lambda domain_id: f"spec:{domain_id}")

        resultado = asyncio.run(tools_knowledge.search_docs("techdocs", "como reiniciar"))

        check("a query chegou inteira", visto.get("query") == "como reiniciar")
        check("o DomainSpec veio do registry", visto.get("domain") == "spec:techdocs")
        check(
            "o assertion é o TOKEN DO CHAMADOR, não a identidade da aplicação",
            visto.get("assertion") == "token-do-chamador",
        )
        check("a resposta carrega citação (regra 4)", bool(resultado.get("sources")))
        check(
            "a citação preserva a fonte e a URL",
            resultado["sources"][0]["source"] == "runbook.md"
            and resultado["sources"][0]["url"] == "https://x/1",
        )

        tools_knowledge.get_access_token = lambda: None
        vazio = asyncio.run(tools_knowledge.search_docs("techdocs", "x"))
        check("sem token, o assertion é None (degrada para identidade da app, não inventa)",
              visto.get("assertion") is None and "sources" in vazio)
    finally:
        tools_knowledge.retrieve = original_retrieve
        tools_knowledge.get_access_token = original_token
        tools_knowledge._domain_lookup = original_lookup

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o trim de ACL acontece sob a identidade de quem perguntou.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
