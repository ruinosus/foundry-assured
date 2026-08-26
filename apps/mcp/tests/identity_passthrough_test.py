"""O token do CHAMADOR chega ao retrieve — é isso que faz o trim de ACL ser dele, e não nosso.

Este é o teste que impede a falha mais cara possível nesta camada: a tool funcionar, devolver
resultado bonito, e estar buscando como a IDENTIDADE DA APLICAÇÃO. Nesse caso o índice
continua carimbado, o `retrieve` continua respondendo, e o usuário recebe documento que não
pode ver — sem erro, sem log, sem sintoma.

`retrieve` usa do `user` exatamente um atributo: `.access_token` (retrieval.py:144, que o
passa como `user_assertion` do OnBehalfOfCredential). Este teste trava essa passagem.

E TRAVA O CONTRÁRIO TAMBÉM, que é o conserto desta rodada. A versão anterior terminava
verificando que, sem token, "o assertion é None (degrada para identidade da app, não inventa)"
— e abençoava exatamente o vazamento que ela existe para impedir: em domínio de fallback,
`user_token=None` faz o `retrieve` mandar `x-ms-enable-elevated-read: true`, isto é, LER TUDO
como a aplicação. Com a auth LIGADA isso tem que FALHAR. Com a auth desligada (dev local)
degradar continua certo — é o comportamento do resto do backend, e é a única razão de o app
subir sem Entra.

O gate de vazamento de verdade (`eval/access_control_test`) precisa de nuvem e de identidades
de teste; ele roda em `security-gates.yml`. Este aqui é o que dá para exigir em todo push.

PORTADO DO MONOLITO SEM UMA ÚNICA MUDANÇA DE ASSERÇÃO — só o caminho do módulo mudou
(`app.modules.mcpserver.internal.tools_knowledge` → `mcp_app.tools_knowledge`). É de propósito:
esta fase tem paridade como critério, e o teste que prova paridade de comportamento não deve
ser reescrito junto com o código que ele guarda. Se alguma asserção precisasse mudar, isso
seria a notícia — e não há nenhuma.

    uv run python -m tests.identity_passthrough_test
"""

from __future__ import annotations

import asyncio
import sys

from fastmcp.exceptions import ToolError

from app.shared import auth as shared_auth
from app.shared.settings import settings
from mcp_app import tools_knowledge


class _Token:
    def __init__(self, raw: str) -> None:
        self.token = raw
        self.claims = {
            "roles": ["Reader"],
            "oid": "00000000-0000-0000-0000-0000000000aa",
            "preferred_username": "quem.perguntou@exemplo.invalid",
        }


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
        # O ator da trilha é lido DENTRO do retrieve (ADR-023), então é aqui que ele tem de
        # estar certo — não depois, quando a requisição já acabou.
        from app.modules.audit.public import actor, actor_detail

        visto["ator"] = actor()
        visto["ator_detalhe"] = actor_detail()
        return [{"index": 1, "source": "runbook.md", "url": "https://x/1", "snippet": "trecho"}]

    original_retrieve = tools_knowledge.retrieve
    original_token = tools_knowledge.get_access_token
    original_lookup = tools_knowledge._domain_lookup
    original_grounded = tools_knowledge._grounded_domains
    original_entra = (settings.entra_tenant_id, settings.entra_api_client_id)
    try:
        tools_knowledge.retrieve = falso_retrieve
        tools_knowledge.get_access_token = lambda: _Token("token-do-chamador")
        tools_knowledge.set_domain_registry(
            lambda domain_id: f"spec:{domain_id}", ("techdocs", "selfwiki")
        )
        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"

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

        # ── a trilha grava QUEM leu (ADR-023) ────────────────────────────────────────────
        # `audit.actor()` lê o contextvar de `shared.auth`, que só o `require_user` do FastAPI
        # escrevia. O caminho MCP não passa por rota FastAPI: sem declarar o chamador, toda
        # leitura por MCP entrava na trilha imutável como `process:app`.
        check(
            f"o ator da trilha é quem perguntou ({visto.get('ator')})",
            visto.get("ator") == "human:quem.perguntou@exemplo.invalid",
        )
        check(
            "e o oid durável vai junto, no detalhe do evento",
            visto.get("ator_detalhe", {}).get("oid") == "00000000-0000-0000-0000-0000000000aa",
        )

        # ── resultado vazio: nada de prosa sem procedência (regra 4) ─────────────────────
        # Zero documento autorizado é resposta legítima do trim de ACL. O que não pode existir é
        # `answer_context` com texto e `sources` vazio — seria fundamentação sem fonte.
        async def retrieve_vazio(query, user, domain, *, top=8):
            return []

        tools_knowledge.retrieve = retrieve_vazio
        vazio = asyncio.run(tools_knowledge.search_docs("techdocs", "nada autorizado"))
        check(
            "trim que não deixa nada passar devolve vazio honesto, nunca texto sem fonte",
            vazio == {"answer_context": "", "sources": []},
        )
        tools_knowledge.retrieve = falso_retrieve

        # ── domínio sem base: recusa nomeada, não KeyError ───────────────────────────────
        for invalido in ("helpdesk", "nao-existe"):
            try:
                asyncio.run(tools_knowledge.search_docs(invalido, "x"))
                check(f"domínio {invalido!r} é recusado", False)
            except ToolError as exc:
                check(
                    f"domínio {invalido!r} é recusado com os válidos junto",
                    "techdocs" in str(exc) and "selfwiki" in str(exc),
                )

        # ── SEM TOKEN, COM AUTH LIGADA: falha, nunca degrada ─────────────────────────────
        visto.clear()
        tools_knowledge.get_access_token = lambda: None
        try:
            asyncio.run(tools_knowledge.search_docs("techdocs", "x"))
            check("auth ligada + sem token do chamador → a busca FALHA", False)
        except ToolError as exc:
            print(f"     ToolError: {exc}")
            check("auth ligada + sem token do chamador → a busca FALHA", True)
        check(
            "e nem chegou ao retrieve (nada de leitura elevada como a aplicação)",
            "assertion" not in visto,
        )

        # ── AUTH DESLIGADA (dev local): degradar é o comportamento do resto do backend ────
        settings.entra_tenant_id = ""
        settings.entra_api_client_id = ""
        shared_auth._current_user.set(None)
        aberto = asyncio.run(tools_knowledge.search_docs("techdocs", "x"))
        check(
            "auth desligada → busca roda sem token (igual ao resto do backend em dev)",
            visto.get("assertion") is None and bool(aberto.get("sources")),
        )
        check(
            "e sem chamador declarado a trilha diz `process:app`, não um humano inventado",
            visto.get("ator") == "process:app",
        )
    finally:
        tools_knowledge.retrieve = original_retrieve
        tools_knowledge.get_access_token = original_token
        tools_knowledge._domain_lookup = original_lookup
        tools_knowledge._grounded_domains = original_grounded
        settings.entra_tenant_id, settings.entra_api_client_id = original_entra
        shared_auth._current_user.set(None)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o trim de ACL acontece sob a identidade de quem perguntou — ou não acontece.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
