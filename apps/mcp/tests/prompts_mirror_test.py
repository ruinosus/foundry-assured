"""O ESPELHO: os prompts que o MCP publica são exatamente os agentes que o `agentdefs` compõe.

O gêmeo, nesta superfície, de `tests.registry.domain_registry_test` do monolito — e existe pela
mesma razão que ele: uma segunda lista não dá erro quando diverge. Se alguém escrever um prompt
literal em `mcp_app/prompts_agentdefs.py`, ou esquecer de publicar um agente novo, o servidor
continua subindo, o `prompts/list` continua respondendo, e o cliente passa a ver um conjunto
diferente do que o produto de fato roda. O sintoma só aparece quando alguém compara à mão — que
é o que este arquivo faz, toda vez.

A FONTE É `composed_agents()`, e não as constantes `*_INSTRUCTIONS` de `agentdefs.public`:
aquelas nascem de um dicionário escrito à mão (`_AGENT_FOR_CONSTANT`), que é justamente o tipo
de lista que este gate existe para não deixar aparecer de novo. `composed_agents()` devolve
TODO agente do escopo, lido dos documentos AgentSchema — é também a função que
`cli/provision_agents.py` usa para publicar no Foundry (SEGUNDA MÁXIMA: um lugar só).

TRÊS VERIFICAÇÕES, e a terceira é a que o teste de espelho do monolito não tinha:

1. Os ids publicados == os ids compostos.
2. O TEXTO publicado é o texto composto (um espelho de nomes com corpo errado passaria em 1).
3. A comparação SABE reprovar — provado por mutação, com um id a mais de cada lado.

    uv run python -m tests.prompts_mirror_test
"""

from __future__ import annotations

import asyncio
import sys

from app.modules.agentdefs.public import composed_agents
from mcp_app import prompts_agentdefs


def _divergencia(publicados: set[str], compostos: set[str]) -> list[str]:
    """As duas metades da divergência, cada uma com o lado que sobra. Isolada em função para o
    teste de mutação chamar a MESMA comparação que o teste real usa — se ele reimplementasse a
    comparação, provaria que a cópia sabe reprovar, não que o gate sabe."""
    problemas = []
    if faltando := sorted(compostos - publicados):
        problemas.append(f"agentes que o `agentdefs` compõe e o MCP NÃO publica: {faltando}")
    if sobrando := sorted(publicados - compostos):
        problemas.append(f"prompts que o MCP publica e o `agentdefs` NÃO compõe: {sobrando}")
    return problemas


async def _publicados() -> dict[str, str]:
    """Os prompts REGISTRADOS pelo módulo real, num servidor descartável: nome → texto.

    Registra pelo mesmo `register` que a composition root chama — não por uma lista montada
    aqui, ou o teste provaria a lista dele.

    A leitura usa `Provider.list_prompts` (a classe-base) em vez de `mcp.list_prompts()` pelo
    mesmo motivo documentado em `tests/instrumentation_matrix_test.py`: a listagem do `FastMCP`
    FILTRA por `auth=`, e sem contexto autorizado ela devolveria zero prompts — o espelho
    ficaria "verde" comparando dois conjuntos vazios.
    """
    from fastmcp import FastMCP
    from fastmcp.server.providers.base import Provider

    mcp = FastMCP("espelho-descartável", tools=[])
    prompts_agentdefs.register(mcp)
    prompts = list(await Provider.list_prompts(mcp))

    textos: dict[str, str] = {}
    for prompt in prompts:
        resultado = await prompt.render({})
        # Um `PromptAgent` não tem argumentos: o corpo é uma mensagem só, e é o texto composto.
        textos[prompt.name] = "".join(
            getattr(m.content, "text", "") or "" for m in resultado.messages
        )
    return textos


def _prova_por_mutacao() -> str | None:
    """Mostra que `_divergencia` reprova nos DOIS sentidos — um prompt a mais só de um lado, e
    um agente a mais só do outro. Sem isto, a verificação 1 poderia estar comparando duas
    cópias da mesma variável e ninguém saberia."""
    base = {"triage", "resolve"}
    if not _divergencia(base | {"inventado"}, base):
        return "um prompt publicado a mais NÃO foi pego"
    if not _divergencia(base, base | {"esquecido"}):
        return "um agente composto e não publicado NÃO foi pego"
    if _divergencia(base, base):
        return "conjuntos idênticos foram reprovados (falso positivo)"
    return None


def main() -> int:
    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    compostos = composed_agents()
    publicados = asyncio.run(_publicados())

    print(f"  · agentes compostos ({len(compostos)}): {', '.join(sorted(compostos))}")
    print(f"  · prompts publicados ({len(publicados)}): {', '.join(sorted(publicados))}")

    # ── 1 · os ids são os mesmos ────────────────────────────────────────────────────────
    problemas = _divergencia(set(publicados), set(compostos))
    check(
        "os prompts publicados são exatamente os agentes compostos"
        + (f" — {' | '.join(problemas)}" if problemas else ""),
        not problemas,
    )

    # ── 1b · `prompt_ids()` é a mesma resposta ──────────────────────────────────────────
    # `register` e o gate leem a mesma função; se `prompt_ids()` divergisse do que `register`
    # publica, o gate estaria verde sobre uma lista que ninguém serve.
    check(
        "`prompt_ids()` responde o mesmo que o registro real",
        set(prompts_agentdefs.prompt_ids()) == set(publicados),
    )

    # ── 2 · o TEXTO é o composto, não um resumo nem um literal ──────────────────────────
    divergentes = sorted(
        nome
        for nome, texto in publicados.items()
        if nome in compostos and texto != compostos[nome][0]
    )
    check(
        "o corpo de cada prompt é o texto COMPOSTO pelo agentdefs"
        + (f" — DIVERGEM: {', '.join(divergentes)}" if divergentes else ""),
        not divergentes,
    )

    # ── 3 · a comparação sabe reprovar ──────────────────────────────────────────────────
    problema = _prova_por_mutacao()
    check(
        "a comparação é capaz de reprovar (provado por mutação, nos dois sentidos)"
        + (f" — {problema}" if problema else ""),
        problema is None,
    )

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print(f"\n✅ {len(publicados)} prompts publicados, todos derivados da fonte única.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
