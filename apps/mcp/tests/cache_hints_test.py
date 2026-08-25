"""O hint de cache (SEP-2549) alcança as LISTAGENS e nunca `resources/read` — medido no fio.

A Fase 5 recusou o cache com a medição de que o botão do FastMCP é uniforme e portanto ligaria
TTL também para `resources/read` — o documento integral com ACL, cuja leitura é o que produz o
evento da trilha (ADR-023). A recusa caiu quando a medição foi completada um andar abaixo: o
mapa de hints do SDK é **por método** (`Server.cache_hints`, consultado em `runner.py:357` com
`.get(method)`), e quem é uniforme é só o atalho do construtor. `mcp_app/cache_hints.py` escreve
a decisão inteira; este arquivo é a prova dela.

ESTE GATE NÃO OLHA O ATRIBUTO — OLHA O FIO. Um teste que conferisse
`mcp._mcp_server.cache_hints` ficaria verde para sempre a partir do dia em que o FastMCP
renomeasse o seam: o hint sumiria do fio e o dicionário que o teste lê continuaria existindo,
porque o teste o leria do mesmo objeto que o código escreve. Aqui todo `ttlMs` vem de uma
resposta de protocolo recebida por um `Client` de verdade, em memória. Se o seam sumir, as
listagens voltam a `ttlMs=0` e a verificação 3 fica vermelha.

AS QUATRO PROPRIEDADES, e por que nenhuma se prova sozinha:

  1. `tools/call` NÃO é cacheável nesta versão do protocolo. É o que faz o cache alcançar só a
     vitrine: toda chamada chega aqui e revalida papel, tenant e ACL. Se o SDK um dia tornar
     `tools/call` cacheável, esta linha fica vermelha ANTES de o produto passar a servir
     resposta de busca do armazenamento do cliente.
  2. `resources/read` É cacheável — é a superfície que o TTL alcançaria, e é por isso que ela
     precisa ser excluída de propósito. Se o SDK tirá-la da lista, a exclusão vira código morto
     e esta linha avisa.
  3. NO FIO: as listagens saem com `ttlMs` > 0 e `resources/read` sai com `ttlMs = 0` — o mesmo
     valor de um servidor que nunca ligou cache. É a verificação central.
  4. Escopo `private` em tudo que recebe hint. `public` autorizaria compartilhar entre contextos
     de autorização — e as listagens deste servidor são FILTRADAS por papel e por tenant. A
     biblioteca aceita `public` sem erro e sem aviso (provado por mutação abaixo), então o freio
     é este gate.

PROVA POR MUTAÇÃO, e ela é dupla aqui. Uma listagem com `ttlMs` positivo poderia ser um acidente
do default; um `resources/read` com `ttlMs=0` poderia ser vácuo (nenhum hint funcionando em
lugar nenhum). Por isso o teste monta DOIS servidores descartáveis ao lado do real: um sem cache
(mostra que 0 é o valor de repouso, inclusive nas listagens) e um com o atalho uniforme
`cache_ttl=` (mostra `resources/read` recebendo TTL — o desfecho que a exclusão evita).

Offline e sem daemon: `Client(mcp)` é o transporte em memória do próprio fastmcp, e com
`ENTRA_*` em branco não há provider de auth. Zero rede.

    uv run python -m tests.cache_hints_test
"""

from __future__ import annotations

import asyncio
import sys

from fastmcp import Client

#: O que uma resposta de repouso carrega. `CacheHint.ttl_ms` tem default 0 e o modelo de
#: resultado também, então "sem hint" e "hint de 0ms" são indistinguíveis no fio — e é
#: exatamente por isso que excluir `resources/read` deixa aquele método BYTE-IDÊNTICO ao de
#: antes desta fase, em vez de trocá-lo por um valor novo.
SEM_TTL = 0


async def _do_fio(mcp) -> dict[str, tuple[int | None, str | None]]:
    """`(ttlMs, cacheScope)` de cada método, lidos de respostas de protocolo de verdade.

    Usa `client.session.*` (a sessão de baixo nível) e não os atalhos do `Client`: os atalhos
    devolvem só o conteúdo — a lista de tools, o conteúdo do recurso —, e os campos de cache
    moram no ENVELOPE do resultado, que é o que precisa ser medido.
    """
    async with Client(mcp) as client:
        medidas = {}
        for metodo, chamada in (
            ("tools/list", client.session.list_tools()),
            ("prompts/list", client.session.list_prompts()),
            ("resources/read", client.session.read_resource("cache-test://sonda")),
        ):
            resultado = await chamada
            medidas[metodo] = (
                getattr(resultado, "ttl_ms", None),
                getattr(resultado, "cache_scope", None),
            )
        return medidas


def _servidor_descartavel(**kwargs):
    """Um FastMCP mínimo com uma tool e um recurso, para as duas provas por mutação.

    Precisa das duas superfícies porque as duas metades da decisão são medidas em métodos
    diferentes: `tools/list` é o que DEVE ganhar TTL e `resources/read` é o que NÃO deve.
    """
    from fastmcp import FastMCP

    servidor = FastMCP("cache-descartável", tools=[], **kwargs)

    @servidor.tool
    def sonda() -> str:
        return "ok"

    @servidor.resource("cache-test://sonda")
    def documento() -> str:
        return "conteúdo"

    return servidor


def main() -> int:
    from mcp_types.methods import CACHEABLE_METHODS

    from app.shared.settings import settings
    from mcp_app import cache_hints, resources_knowledge, tools_knowledge
    from mcp_app.auth import build_auth
    from mcp_app.main import build_mcp, wire_registry

    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    # --- 1 e 2 · o que o protocolo torna cacheável, que é o que decide o desenho -------------
    check(
        f"`tools/call` NÃO é cacheável ({len(CACHEABLE_METHODS)} métodos são: "
        f"{', '.join(sorted(CACHEABLE_METHODS))}) — o cache alcança a vitrine, nunca a porta",
        "tools/call" not in CACHEABLE_METHODS,
    )
    check(
        "`resources/read` É cacheável — é a superfície com ACL que a exclusão existe para tirar",
        "resources/read" in CACHEABLE_METHODS,
    )

    # --- 3 · O FIO DO SERVIDOR REAL — a verificação central ---------------------------------
    wire_registry()
    real = build_mcp(build_auth(settings.mcp_public_base_url))
    tools_knowledge.register(real)
    resources_knowledge.register(real)

    # O recurso-sonda entra NO SERVIDOR REAL porque `document://{domain}/{name}` é um TEMPLATE:
    # ler um documento de verdade exigiria backend, ACL e blob. O que está sob medição é o
    # ENVELOPE de `resources/read`, que o runner preenche por MÉTODO — não por recurso. Um
    # recurso trivial mede o mesmo método pelo mesmo caminho, sem rede.
    @real.resource("cache-test://sonda")
    def _sonda() -> str:
        return "conteúdo"

    medido = asyncio.run(_do_fio(real))
    print(f"     fio do servidor real: {medido}")

    ttl_esperado = cache_hints.TTL_SEGUNDOS * 1000
    check(
        f"NO FIO: `tools/list` sai com ttlMs={ttl_esperado} (medido: {medido['tools/list'][0]})",
        medido["tools/list"][0] == ttl_esperado,
    )
    check(
        f"NO FIO: `prompts/list` sai com ttlMs={ttl_esperado} "
        f"(medido: {medido['prompts/list'][0]})",
        medido["prompts/list"][0] == ttl_esperado,
    )
    check(
        "NO FIO: `resources/read` sai com ttlMs=0 — o documento com ACL chega SEMPRE aqui, e é "
        f"a chegada que vira evento na trilha (medido: {medido['resources/read'][0]})",
        medido["resources/read"][0] == SEM_TTL,
    )

    # --- 4 · escopo: nunca `public` ---------------------------------------------------------
    escopos = {m: escopo for m, (ttl, escopo) in medido.items() if ttl}
    check(
        f"tudo que recebe hint sai com escopo `private` (medido: {escopos}) — `public` "
        "autorizaria servir a listagem filtrada de um chamador a outro",
        set(escopos.values()) == {cache_hints.ESCOPO} == {"private"},
    )

    # --- prova por mutação A · 0 é o valor de REPOUSO, não um efeito nosso -------------------
    repouso = asyncio.run(_do_fio(_servidor_descartavel()))
    check(
        f"servidor SEM cache: tudo em ttlMs=0, listagens inclusive (medido: {repouso}) — é o "
        "que torna `resources/read` byte-idêntico ao de antes desta fase",
        {ttl for ttl, _ in repouso.values()} == {SEM_TTL},
    )

    # --- prova por mutação B · o atalho uniforme alcança `resources/read` --------------------
    # É a medição que fundamentou a recusa da Fase 5 e que continua verdadeira: quem usar
    # `cache_ttl=` no construtor liga o TTL para o documento com ACL junto. Mantê-la aqui é o
    # que impede alguém de "simplificar" `cache_hints.aplicar` de volta para o atalho.
    uniforme = asyncio.run(_do_fio(_servidor_descartavel(cache_ttl=60)))
    check(
        f"o atalho `cache_ttl=` do construtor ALCANÇA `resources/read` (medido: {uniforme}) — "
        "é por isso que o mapa por método existe, e por que trocá-lo pelo atalho é regressão",
        uniforme["resources/read"][0] == 60_000 and uniforme["tools/list"][0] == 60_000,
    )

    # --- prova por mutação C · a biblioteca não freia o escopo perigoso ----------------------
    from fastmcp import FastMCP

    publico = FastMCP("cache-público-descartável", tools=[], cache_ttl=60, cache_scope="public")
    aceitou_public = {
        h.scope for h in dict(getattr(publico._mcp_server, "cache_hints", {})).values()
    } == {"public"}
    check(
        "a biblioteca aceita `cache_scope='public'` sem erro nem aviso — o freio contra "
        "compartilhar listagem entre identidades é ESTE gate, não ela",
        aceitou_public,
    )

    # --- a cobertura é DERIVADA, não escrita -------------------------------------------------
    check(
        f"o mapa cobre exatamente os cacheáveis menos {sorted(cache_hints.SEM_HINT)} — derivado "
        "de `CACHEABLE_METHODS`, então um método novo do SDK não passa despercebido",
        set(cache_hints.hints()) == set(CACHEABLE_METHODS) - cache_hints.SEM_HINT,
    )

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        print(
            "   Se a intenção foi mexer no cache: leia `mcp_app/cache_hints.py`. A pergunta que "
            "decide não é o TTL — é se a resposta cacheada é catálogo ou conteúdo controlado."
        )
        return 1
    print("\n✅ o hint cobre as listagens; `resources/read` continua chegando aqui a cada leitura.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
