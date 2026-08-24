"""A tool `search_docs` — busca fundamentada, com o trim de ACL do chamador.

ESTA TOOL NÃO BUSCA. Ela chama `knowledge.public.retrieve`, que é onde o trim de ACL por
documento acontece (regra 6: acesso é DADO, declarado na fonte). Reimplementar recuperação
aqui criaria duas respostas para a mesma pergunta — e a divergência não daria erro, só faria
o MCP e a interface discordarem sobre o que o usuário pode ver.

`retrieve` usa do `user` apenas `.access_token`, como `user_assertion` do OnBehalfOfCredential
(retrieval.py:144). O token do chamador MCP vem de `get_access_token()` e é embrulhado em
`_Caller` — um adaptador de um atributo, não uma abstração.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.server.dependencies import get_access_token

from app.modules.knowledge.public import retrieve
from app.modules.mcpserver.internal.authz import role_check

#: Empurrado pela composition root: `domain_spec` mora em `app/registry.py`, e um módulo não
#: pode importar da camada de composição (ADR-017). Mesmo padrão de
#: `knowledge.api.set_domain_lookup`.
_domain_lookup: Callable[[str], Any] | None = None


def set_domain_lookup(fn: Callable[[str], Any]) -> None:
    global _domain_lookup
    _domain_lookup = fn


class _Caller:
    """O único atributo que `retrieve` lê do usuário."""

    def __init__(self, access_token: str | None) -> None:
        self.access_token = access_token


async def search_docs(domain: str, query: str) -> dict[str, Any]:
    """Busca na base de conhecimento do domínio, com o controle de acesso do chamador."""
    if _domain_lookup is None:
        raise RuntimeError("domain lookup não registrado — a composition root não chamou set_domain_lookup")

    token = get_access_token()
    caller = _Caller(getattr(token, "token", None) if token is not None else None)
    linhas = await retrieve(query, caller, _domain_lookup(domain))

    return {
        "answer_context": "\n\n".join(l.get("snippet", "") for l in linhas),
        # Regra 4 vira FORMATO aqui: quem consome recebe as fontes como dado estruturado, não
        # como texto que ele precisa reparsear para saber de onde veio a resposta.
        "sources": [
            {
                "index": l.get("index"),
                "source": l.get("source"),
                "url": l.get("url"),
            }
            for l in linhas
        ],
    }


def register(mcp: FastMCP) -> None:
    mcp.tool(
        search_docs,
        name="search_docs",
        description=(
            "Busca na base de conhecimento de um domínio (techdocs, selfwiki, helpdesk). "
            "Devolve trechos e as fontes que os sustentam. O resultado já vem filtrado pelo "
            "que o usuário autenticado tem permissão de ler."
        ),
        tags={"knowledge", "read"},
        auth=role_check("Reader", "Author", "Approver", "Admin"),
    )
