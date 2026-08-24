"""A tool `search_docs` — busca fundamentada, com o trim de ACL do chamador.

ESTA TOOL NÃO BUSCA. Ela chama `knowledge.public.retrieve`, que é onde o trim de ACL por
documento acontece (regra 6: acesso é DADO, declarado na fonte). Reimplementar recuperação
aqui criaria duas respostas para a mesma pergunta — e a divergência não daria erro, só faria
o MCP e a interface discordarem sobre o que o usuário pode ver.

`retrieve` usa do `user` apenas `.access_token`, como `user_assertion` do OnBehalfOfCredential
(retrieval.py:144). O token do chamador MCP vem de `get_access_token()` e é embrulhado em
`_Chamador` — um adaptador de atributos, não uma abstração.

O `_Chamador` também é DECLARADO como usuário da requisição (`shared.auth.set_current_user`).
Sem isso a trilha de auditoria da ADR-023 — gravada lá dentro do `retrieve`, via
`audit.actor()`, que lê o mesmo contextvar — registrava toda leitura por MCP como
`process:app`: acesso decidido pela identidade certa e registrado com a identidade errada.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

from app.modules.knowledge.public import retrieve
from app.modules.mcpserver.internal.authz import role_check
from app.shared.auth import set_current_user
from app.shared.settings import settings

#: Empurrados pela composition root: `domain_spec` e a lista de domínios com base de
#: conhecimento moram em `app/registry.py`, e um módulo não pode importar da camada de
#: composição (ADR-017). Mesmo padrão de `knowledge.api.set_domain_lookup`.
_domain_lookup: Callable[[str], Any] | None = None
_grounded_domains: tuple[str, ...] = ()


def set_domain_registry(lookup: Callable[[str], Any], grounded: tuple[str, ...]) -> None:
    """Recebe da composition root o que o registry sabe: como resolver um domínio, e QUAIS
    domínios têm base de conhecimento.

    Os dois vêm juntos, num empurrão só, porque são a mesma informação vista de dois ângulos —
    e porque a lista de domínios grounded não pode ser escrita aqui à mão. Uma segunda lista
    divergiria do `DOMAIN_KINDS` no primeiro domínio novo, e a divergência não dá erro: só faz
    a tool anunciar domínio que não existe (ou esconder um que existe).
    """
    global _domain_lookup, _grounded_domains
    _domain_lookup = lookup
    _grounded_domains = tuple(grounded)


class _Chamador:
    """Quem perguntou, no vocabulário que o resto do backend já lê.

    `access_token` é o único atributo que o `retrieve` usa (OBO). Os demais são os que
    `audit.actor()`/`actor_detail()` e `shared.auth.current_roles()` leem do usuário do FastAPI
    — vêm das claims do MESMO token do Entra, então a trilha grava a mesma identidade que
    gravaria se a pergunta tivesse entrado pela web.
    """

    def __init__(self, access_token: str | None, claims: dict[str, Any]) -> None:
        self.access_token = access_token
        self.oid = str(claims.get("oid") or "")
        self.preferred_username = str(claims.get("preferred_username") or "")
        self.email = str(claims.get("email") or "")
        self.roles = list(claims.get("roles") or [])


async def search_docs(domain: str, query: str) -> dict[str, Any]:
    """Busca na base de conhecimento do domínio, com o controle de acesso do chamador."""
    if _domain_lookup is None or not _grounded_domains:
        raise RuntimeError(
            "registry de domínios não registrado — a composition root não chamou set_domain_registry"
        )
    # DOMÍNIO INVÁLIDO É ERRO DO CHAMADOR, com o nome dos válidos junto. Antes, um domínio
    # desconhecido chegava ao `domain_spec` e voltava como `KeyError`; e um domínio sem base
    # (helpdesk, platform) montava `.../indexes/None/docs/search` no fallback do `retrieve`.
    if domain not in _grounded_domains:
        raise ToolError(
            f"domínio sem base de conhecimento: {domain!r} — "
            f"válidos: {', '.join(_grounded_domains)}"
        )

    token = get_access_token()
    bruto = getattr(token, "token", None) if token is not None else None

    # FALHA FECHADA COM A AUTH LIGADA. Sem token do chamador, o `retrieve` cai no ramo
    # "identidade da aplicação": em domínio de fallback ele manda `x-ms-enable-elevated-read`,
    # isto é, LÊ TUDO como a app — sem erro, sem log, sem sintoma. Degradar assim é correto no
    # dev local (a auth está desligada e é o comportamento do resto do backend), e é vazamento
    # em produção. A distinção é `settings.auth_enabled`, a mesma que governa todo o resto.
    if settings.auth_enabled and not bruto:
        raise ToolError("busca sem identidade do chamador: envie o token do Entra")

    chamador = _Chamador(bruto, getattr(token, "claims", None) or {})
    if bruto:
        # Só com token: com a auth desligada não HÁ chamador, e declarar um sem identidade faria
        # a trilha gravar um `human:` inventado onde `process:app` é a verdade.
        set_current_user(chamador)

    linhas = await retrieve(query, chamador, _domain_lookup(domain))

    return {
        # NUNCA TEXTO SEM FONTE (regra 4). O contexto é montado a partir das MESMAS linhas que
        # viram `sources`, então zero fonte implica contexto vazio por construção — o caso em
        # que o trim de ACL não deixou nada passar devolve uma resposta vazia honesta, não prosa
        # sem procedência.
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
    """Registra a tool. Exige que a composition root já tenha empurrado o registry.

    A ordem é real: `include_routers(app)` chama `set_domain_registry` antes de `build_mcp_app`
    montar o servidor. Falhar alto aqui é de propósito — com a lista vazia a descrição anunciaria
    "válidos: " e o chamador ficaria sem saber o que passar.
    """
    if not _grounded_domains:
        raise RuntimeError(
            "set_domain_registry precisa rodar antes de registrar as tools do MCP"
        )
    mcp.tool(
        search_docs,
        name="search_docs",
        description=(
            # A LISTA VEM DO REGISTRY, não de um literal. A descrição já citou "helpdesk", que
            # não tem base de conhecimento nenhuma — a busca cairia em
            # `.../indexes/None/docs/search`. Tool que anuncia domínio inexistente é pior que
            # tool ausente: o chamador tenta, recebe erro, e culpa a pergunta.
            f"Busca na base de conhecimento de um domínio ({', '.join(_grounded_domains)}). "
            "Devolve trechos e as fontes que os sustentam. O resultado já vem filtrado pelo "
            "que o usuário autenticado tem permissão de ler."
        ),
        tags={"knowledge", "read"},
        auth=role_check("Reader", "Author", "Approver", "Admin"),
    )
