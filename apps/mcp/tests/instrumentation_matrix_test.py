"""Toda tool MCP é autenticada por papel e DECLARA o que grava — o gêmeo, neste app, do gate
`tests/architecture/instrumentation_matrix_test.py` do monolito.

POR QUE ESTE GATE EXISTE AQUI TAMBÉM. A Fase 0c tirou a linha `/mcp` da matriz do monolito — o
comentário que ficou no lugar dela diz, corretamente, que a superfície é `apps/mcp` agora e que
"a de lá é coberta pelos gates de `apps/mcp/tests/`". Isso nunca foi verdade: nenhum teste deste
app perguntava "toda tool tem `auth=`?" nem "toda tool que existe está declarada em algum
lugar?" — as duas metades que a matriz do monolito prova. `identity_passthrough_test` prova, de
lado, que a ÚNICA tool de hoje (`search_docs`) grava citação e trilha — mas prova por ter escrito
o teste à mão, não por um mecanismo que reprova sozinho quando uma tool NOVA esquece uma das
duas. Este arquivo é esse mecanismo.

O CUIDADO QUE A VERSÃO DO MONOLITO NÃO TEVE, E A FORMA ESPELHADA QUE A ARMADILHA TOMA AQUI. Lá,
uma rota sem auth se tornava invisível à captura (perdia `.methods`), e "nenhuma sem auth"
passava vazio sobre zero rotas olhadas. Aqui a armadilha é a MESMA ideia com o sinal trocado —
medida, não deduzida (ver `_prova_por_mutacao`): `FastMCP.list_tools()` só filtra a tool que TEM
`auth=` e falha o check (ela some quando não há contexto autorizado); uma tool que ESQUECEU
`auth=` nunca é filtrada e continua sempre visível. Ou seja, descobrir tools por
`mcp.list_tools()` sem contexto faz o CONTRÁRIO do que se espera: a tool bem configurada
(`search_docs`) desaparece da contagem, e a mal configurada permanece — corrompendo exatamente o
cruzamento que a verificação 2 (declarada vs. encontrada) depende para pegar drift. Por isso a
descoberta usa `Provider.list_tools(mcp)` — o método da CLASSE-BASE, chamado sem passar pelo
override do `FastMCP` — que devolve o registro CRU, com `tool.auth` do jeito que
`mcp.tool(..., auth=...)` deixou, filtro nenhum aplicado.

    uv run python -m tests.instrumentation_matrix_test
"""

from __future__ import annotations

import sys

#: As colunas que a matriz do monolito usa. Search_docs responde às seis; a maioria é `n/a`
#: porque esta superfície não é um agente conversacional — é uma tool de busca avulsa.
COLUNAS = ("conversa", "tokens", "referencias", "chamado", "trilha", "caso_de_uso")

#: A MATRIZ. Uma linha por tool registrada hoje — `search_docs` é a única. `True` = grava hoje;
#: string = não grava, e o texto diz por quê (mesma convenção do monolito).
MATRIZ: dict[str, dict[str, object]] = {
    "search_docs": {
        "conversa": "n/a: chamada de tool avulsa — não há objeto de conversa para persistir",
        "tokens": "n/a: search_docs só busca, não chama modelo — não há uso de token a contar",
        # Regra 4 (CLAUDE.md): toda resposta fundamentada carrega citação. `identity_passthrough_test`
        # trava isto linha a linha — `sources` presente, e vazio honesto (não prosa sem fonte)
        # quando o trim de ACL não deixa nada passar.
        "referencias": True,
        "chamado": "n/a: search_docs não abre chamado",
        # ADR-023: o ator da trilha é QUEM PERGUNTOU, não `process:app` — gravado dentro de
        # `retrieve` via `audit.actor()`, que lê o `_Chamador` que `search_docs` declara antes de
        # buscar. `identity_passthrough_test` trava os dois lados (com token e sem).
        "trilha": True,
        "caso_de_uso": "n/a: módulo usecases não se aplica a uma busca avulsa por MCP",
    },
}


def _tools_sem_auth(tools) -> list[str]:
    """Nomes das tools SEM `auth=` — a checagem estrutural, isolada para o teste de mutação
    poder chamar a mesma função contra um registro descartável."""
    return sorted(t.name for t in tools if t.auth is None)


async def _registro_cru(mcp):
    """O registro de tools TAL COMO FOI FEITO, sem o filtro de auth que `FastMCP.list_tools()`
    aplica antes de devolver — ver a nota grande no topo do arquivo sobre por que isto importa.
    """
    from fastmcp.server.providers.base import Provider

    return list(await Provider.list_tools(mcp))


async def _prova_por_mutacao() -> str | None:
    """Registra duas tools num servidor descartável — uma SEM `auth=` (o defeito que a
    verificação 1 tem que pegar) e uma COM `auth=` (o controle, que representa `search_docs`) —
    e mostra duas coisas medidas, não afirmadas:

    1. `_tools_sem_auth` sobre o registro CRU acha exatamente a tool sem dono. Se esta função não
       encontrar nada, a verificação 1 do `main()` seria decorativa.
    2. A listagem FILTRADA (`FastMCP.list_tools()`, sem contexto de auth) faz o oposto do que se
       esperaria: perde a tool COM dono (ela falha no check de auth e é removida) e MANTÉM a tool
       sem dono (que nunca é checada, porque `tool.auth is None` pula o filtro). É a prova de que
       descobrir por aí, em vez de pelo registro cru, corromperia o cruzamento da verificação 2.

    Devolve a mensagem de falha, ou `None` se as duas mutações foram corretamente pegas.
    """
    from fastmcp import FastMCP

    from mcp_app.auth import require_any_role

    descartavel = FastMCP("mutação-descartável", tools=[])

    def tool_sem_dono() -> str:
        return "nunca deveria existir sem auth="

    def tool_com_dono() -> str:
        return "o controle — representa search_docs"

    descartavel.tool(tool_sem_dono, name="tool_sem_dono")  # sem `auth=`, de propósito
    descartavel.tool(tool_com_dono, name="tool_com_dono", auth=require_any_role("Reader"))

    cru = await _registro_cru(descartavel)
    achadas = _tools_sem_auth(cru)
    if achadas != ["tool_sem_dono"]:
        return (
            "a mutação não reproduziu o defeito esperado no registro cru — "
            f"achadas={achadas!r} (esperava só 'tool_sem_dono')"
        )

    filtrada = sorted(t.name for t in await descartavel.list_tools())
    if filtrada != ["tool_sem_dono"]:
        return (
            "a listagem filtrada deveria perder a tool COM auth e manter a SEM auth "
            f"(a armadilha) — veio {filtrada!r}"
        )

    return None


async def _superficies() -> list:
    """As tools registradas HOJE pela composition root real (`mcp_app.main`), com a MESMA
    fiação que `build_app()` usa — nada de registrar a tool à mão aqui, ou o teste provaria a
    tool que ELE monta, não a que o app monta."""
    from app.shared.settings import settings
    from mcp_app import tools_knowledge
    from mcp_app.auth import build_auth
    from mcp_app.main import build_mcp, wire_registry

    wire_registry()
    mcp = build_mcp(build_auth(settings.mcp_public_base_url))
    tools_knowledge.register(mcp)
    return await _registro_cru(mcp)


def main() -> int:
    import asyncio

    from app.shared.settings import settings

    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    original = (
        settings.entra_tenant_id,
        settings.entra_api_client_id,
        settings.mcp_public_base_url,
    )
    try:
        # Auth LIGADA para a descoberta: sem `ENTRA_*` a tool nasce sem `auth=` nenhum (dev
        # local degrada aberto — ver `require_any_role`), e a verificação 2 abaixo não
        # significaria nada.
        settings.entra_tenant_id = "11111111-1111-1111-1111-111111111111"
        settings.entra_api_client_id = "22222222-2222-2222-2222-222222222222"
        settings.mcp_public_base_url = "http://testserver"

        tools = asyncio.run(_superficies())
        nomes = sorted(t.name for t in tools)
        check(f"a descoberta achou tools ({len(nomes)}: {', '.join(nomes)})", len(nomes) >= 1)

        # --- 1 · toda tool exige papel do Entra --------------------------------------------
        sem_auth = _tools_sem_auth(tools)
        check(
            "nenhuma tool sem `auth=`"
            + (f" — SEM AUTH: {', '.join(sem_auth)}" if sem_auth else ""),
            not sem_auth,
        )

        # --- prova de que a verificação acima SABE falhar (não é vácuo por filtro) ----------
        problema_mutacao = asyncio.run(_prova_por_mutacao())
        check(
            "a checagem 1 é capaz de reprovar (provado por mutação, servidor descartável)"
            + (f" — {problema_mutacao}" if problema_mutacao else ""),
            problema_mutacao is None,
        )

        # --- 2 · nenhuma tool órfã, dos dois lados ------------------------------------------
        nao_declaradas = sorted(set(nomes) - set(MATRIZ))
        check(
            "toda tool registrada está declarada na matriz"
            + (f" — FALTAM: {', '.join(nao_declaradas)}" if nao_declaradas else ""),
            not nao_declaradas,
        )
        orfas = sorted(set(MATRIZ) - set(nomes))
        check(
            "nenhuma declaração aponta para tool inexistente"
            + (f" — ÓRFÃS: {', '.join(orfas)}" if orfas else ""),
            not orfas,
        )

        # --- 3 · toda declaração responde a TODAS as colunas, e `n/a` tem motivo -----------
        incompletas: list[str] = []
        vazias: list[str] = []
        for nome, linha in MATRIZ.items():
            faltando = [c for c in COLUNAS if c not in linha]
            if faltando:
                incompletas.append(f"{nome}: {', '.join(faltando)}")
            for coluna, valor in linha.items():
                if valor is not True and not str(valor).strip():
                    vazias.append(f"{nome}.{coluna}")
        check(
            "toda linha responde a todas as colunas"
            + (f" — INCOMPLETAS: {'; '.join(incompletas)}" if incompletas else ""),
            not incompletas,
        )
        check(
            "toda lacuna declarada tem motivo escrito"
            + (f" — VAZIAS: {', '.join(vazias)}" if vazias else ""),
            not vazias,
        )
    finally:
        (
            settings.entra_tenant_id,
            settings.entra_api_client_id,
            settings.mcp_public_base_url,
        ) = original

    total = len(MATRIZ) * len(COLUNAS)
    grava = sum(1 for l in MATRIZ.values() for v in l.values() if v is True)
    na = sum(1 for l in MATRIZ.values() for v in l.values() if str(v).startswith("n/a:"))
    lacuna = total - grava - na
    print(f"\n  cobertura: {grava}/{total} gravam · {na} não se aplicam · {lacuna} lacunas conhecidas")

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ toda tool MCP exige papel do Entra e declara o que grava.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
