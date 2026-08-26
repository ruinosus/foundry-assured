"""A tool `search_docs` — busca fundamentada, com o trim de ACL do chamador.

ESTA TOOL NÃO BUSCA. Ela chama `knowledge.public.retrieve`, que é onde o trim de ACL por
documento acontece (regra 6: acesso é DADO, declarado na fonte). Reimplementar recuperação
aqui criaria duas respostas para a mesma pergunta — e a divergência não daria erro, só faria
o MCP e a interface discordarem sobre o que o usuário pode ver.

`retrieve` usa do `user` apenas `.access_token`, como `user_assertion` do OnBehalfOfCredential
(knowledge/internal/retrieval.py). O token do chamador MCP vem de `get_access_token()` e é
traduzido por `mcp_app.caller` — que também DECLARA o chamador como usuário da requisição, para
que a trilha da ADR-023 grave quem perguntou em vez de `process:app`. Esse trecho morava aqui e
saiu para `caller.py` quando o resource do documento integral passou a precisar do mesmo: uma
implementação, três chamadores (tool, resource, completion).

PORTADO DO MONOLITO (`app/modules/mcpserver/internal/tools_knowledge.py`) sem mudança de
comportamento. O que mudou é de onde vem o empurrão do registry — ver `set_domain_registry`.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from fastmcp.server.dependencies import get_access_token

from app.modules.knowledge.public import retrieve
from mcp_app import sessions
from mcp_app.auth import require_any_role
from mcp_app.caller import identidade_do_chamador
from mcp_app.tenant_gate import recusa_de_tenant

#: Empurrados pela composition root DESTE app (`mcp_app/main.py`), que é quem pode ver o
#: registry de domínios. Continua sendo empurrão e não import direto por dois motivos: mantém
#: este arquivo sem conhecer a topologia (ele só precisa resolver um id), e é o que deixa o
#: teste de identity passthrough injetar um registry falso sem subir o backend inteiro.
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

    # Falha fechada com a auth ligada, degrada aberto sem ela, e declara o chamador para a
    # trilha — as três coisas moram em `caller.identidade_do_chamador`, ver o docstring de lá.
    chamador = identidade_do_chamador(
        get_access_token(), erro="busca sem identidade do chamador: envie o token do Entra"
    )

    # MODO SHARED: resolver o tenant E cobrar o entitlement. As duas coisas, sempre juntas —
    # resolver sem cobrar serve domínio não licenciado, que é pior que falhar. A regra mora em
    # `mcp_app.tenant_gate`, que é a MESMA do `require_domain` do FastAPI (ADR-010), e agora
    # tem quatro consumidores: esta tool, o resource `document://` e as duas completions dele.
    # Aqui só se traduz a recusa para o vocabulário de tool.
    motivo = recusa_de_tenant(chamador, domain)
    if motivo:
        raise ToolError(motivo)

    linhas = await retrieve(query, chamador, _domain_lookup(domain))

    fontes = [
        {
            "index": l.get("index"),
            "source": l.get("source"),
            "url": l.get("url"),
        }
        for l in linhas
    ]

    # AS CITAÇÕES FICAM NA SESSÃO DO CHAMADOR, para o app de evidências poder mostrá-las sem
    # refazer a busca (refazê-la daria outro conjunto, e uma tabela de evidências que discorda da
    # evidência é pior que nenhuma). Nada de novo é revelado: são os MESMOS três campos que
    # acabaram de ir na resposta, ao mesmo chamador. Não levanta nunca — um cache indisponível
    # não pode transformar uma busca bem-sucedida em erro. Ver `mcp_app/sessions.py`.
    await sessions.guardar_evidencia(domain, fontes)

    return {
        # NUNCA TEXTO SEM FONTE (regra 4). O contexto é montado a partir das MESMAS linhas que
        # viram `sources`, então zero fonte implica contexto vazio por construção — o caso em
        # que o trim de ACL não deixou nada passar devolve uma resposta vazia honesta, não prosa
        # sem procedência.
        "answer_context": "\n\n".join(l.get("snippet", "") for l in linhas),
        # Regra 4 vira FORMATO aqui: quem consome recebe as fontes como dado estruturado, não
        # como texto que ele precisa reparsear para saber de onde veio a resposta. É a MESMA
        # lista que foi para a sessão — uma construção, dois destinos, para a tabela de
        # evidências não poder divergir da resposta que ela diz sustentar.
        "sources": fontes,
    }


def register(mcp: FastMCP, *, task: bool = False) -> None:
    """Registra a tool. Exige que a composition root já tenha empurrado o registry.

    Falhar alto aqui é de propósito — com a lista vazia a descrição anunciaria "válidos: " e o
    chamador ficaria sem saber o que passar.

    `task` VEM DE FORA E NÃO É DECIDIDO AQUI. Ele diz se o servidor tem backend durável e chave
    de cifra para as background tasks (SEP-2663) — a resposta é de `mcp_app.tasks_backend`, e o
    critério de por que é ESTA tool que vira task está escrito lá. Aqui só se repassa, porque
    registrar `task=True` num servidor sem a extensão derruba o HANDSHAKE inteiro, não a
    chamada: os dois lados têm que sair da mesma decisão, no mesmo lugar.

    `task=True` é `mode="optional"`: quem escolhe, chamada a chamada, é o cliente. Um cliente
    que não pede task recebe a resposta síncrona de sempre — nada muda para quem já usa.
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
        auth=require_any_role("Reader", "Author", "Approver", "Admin"),
        task=task,
    )
