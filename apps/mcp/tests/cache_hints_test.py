"""Este servidor NÃO emite hint de cache (SEP-2549) — e o gate existe porque ligar um seria
a única mudança de UMA LINHA, nesta spec inteira, capaz de causar dano em silêncio.

POR QUE ISTO É UM GATE DE ITEM RECUSADO, E NÃO DE ITEM ENTREGUE. A Fase 5 (T7) avaliou
`cache_ttl`/`cache_scope` e recusou. Uma recusa escrita só na spec deixa a arma carregada: quem
amanhã acrescentar `cache_ttl=300` ao construtor não vai ler a spec, vai ler o construtor — e o
construtor aceita, sem aviso, sem erro e sem sintoma. Este arquivo é a recusa em forma
executável.

O QUE FOI MEDIDO (fastmcp 4.0.0b3 + mcp 2.1.0 instalados, regra 1):

1. `tools/call` NÃO É UM MÉTODO CACHEÁVEL. `CacheableMethod` são seis, e a chamada de tool não
   está entre eles. O vazamento que a spec temia — "a resposta de busca de um chamador servida a
   outro, com o trim de ACL feito para o primeiro" — é impossível POR CONSTRUÇÃO nesta versão do
   protocolo. Não porque configuramos bem: porque o botão não alcança essa superfície.

2. O HINT É UNIFORME POR CONSTRUÇÃO. `build_cache_hints` faz
   `dict.fromkeys(get_args(CacheableMethod), hint)` — um valor de servidor para TODOS os métodos
   cacheáveis. Não existe "cachear só as listagens": ligar o TTL para `tools/list` liga junto
   `resources/read`, que aqui é `document://{domain}/{name}` — o documento integral, controlado
   por ACL e registrado na trilha (ADR-023) leitura a leitura, inclusive as NEGADAS.

   É aí que mora o dano real, e ele não é vazamento entre pessoas: é um BURACO NA TRILHA. Um
   hint em `resources/read` autoriza o cliente a servir a leitura do armazenamento dele. Essa
   leitura nunca chega aqui, então nunca vira evento — e o produto passa a afirmar "toda leitura
   de documento controlado fica registrada" sobre leituras que ele não vê mais. Uma revogação de
   acesso também só passa a valer depois do TTL.

3. A PROVA EXIGIDA PARA ENTRAR NÃO É PRODUZÍVEL DESTE LADO. O critério da fase era provar por
   teste que dois chamadores com ACLs diferentes não compartilham entrada de cache. Não há
   entrada de cache aqui para testar: o servidor não guarda nada — ele emite uma DICA, e quem
   guarda (ou não) é o cliente. `cache_scope="private"` é um pedido ao cliente, não uma garantia
   nossa. Sem prova possível, não entra — e é essa a regra que este gate trava.

O gate NÃO proíbe cache para sempre. Ele obriga quem quiser ligá-lo a passar por aqui e
responder ao que está escrito acima — hoje, a resposta que faltaria é o que fazer com a trilha
de `resources/read`.

    uv run python -m tests.cache_hints_test
"""

from __future__ import annotations

import sys
from typing import get_args


def _hints_do_servidor(mcp) -> dict:
    """Os hints que este servidor vai carimbar no fio, lidos de onde eles de fato moram.

    O FastMCP não guarda `cache_ttl`: ele converte no construtor e entrega o mapa ao servidor
    de baixo nível (`LowLevelServer.cache_hints`), que é quem preenche `ttlMs`/`cacheScope` em
    cada resultado cacheável. Ler o mapa final — e não o argumento — é o que faz este gate
    enxergar também um hint que chegue por outro caminho (um `Server(cache_hints=…)` montado à
    mão, por exemplo).
    """
    return dict(getattr(mcp._mcp_server, "cache_hints", {}))


def main() -> int:
    from mcp_types.methods import CacheableMethod

    from app.shared.settings import settings
    from mcp_app.auth import build_auth
    from mcp_app.main import build_mcp

    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    cacheaveis = set(get_args(CacheableMethod))

    # --- 1 · a chamada de tool não é cacheável — o vazamento temido é impossível aqui -------
    check(
        f"`tools/call` não é método cacheável nesta versão ({len(cacheaveis)} são: "
        f"{', '.join(sorted(cacheaveis))})",
        "tools/call" not in cacheaveis,
    )
    # E `resources/read` É — é a superfície controlada por ACL que um TTL alcançaria. Se um dia
    # o SDK tirar `resources/read` da lista, este check fica vermelho e a metade 2 do raciocínio
    # acima precisa ser reescrita antes de a recusa continuar valendo.
    check(
        "`resources/read` É cacheável — é a superfície com ACL que um TTL alcançaria",
        "resources/read" in cacheaveis,
    )

    # --- 2 · o servidor REAL não emite hint nenhum ------------------------------------------
    mcp = build_mcp(build_auth(settings.mcp_public_base_url))
    hints = _hints_do_servidor(mcp)
    check(
        "o servidor deste app não emite hint de cache"
        + (f" — EMITE: {sorted(hints)}" if hints else ""),
        not hints,
    )

    # --- 3 · prova por mutação: o botão é único e alcança o documento com ACL ---------------
    # Sem isto, a verificação 2 poderia estar verde por vácuo (um `cache_hints` que nunca é
    # preenchido por caminho nenhum). Aqui se liga o TTL num servidor descartável e se mostra,
    # medido, as duas propriedades que fundamentam a recusa: o hint cobre TODOS os métodos
    # cacheáveis de uma vez, `resources/read` entre eles.
    from fastmcp import FastMCP

    ligado = FastMCP("cache-descartável", tools=[], cache_ttl=60)
    hints_ligado = _hints_do_servidor(ligado)
    check(
        "com `cache_ttl`, o hint cobre TODOS os métodos cacheáveis (não há 'só as listagens')"
        + (f" — cobriu {sorted(hints_ligado)}" if set(hints_ligado) != cacheaveis else ""),
        set(hints_ligado) == cacheaveis,
    )
    check(
        "e alcança `resources/read` — o documento integral, controlado por ACL e auditado",
        "resources/read" in hints_ligado,
    )

    # --- 4 · nada na biblioteca impede o escopo perigoso ------------------------------------
    # `cache_scope="public"` significa "pode ser compartilhado entre contextos de autorização".
    # A biblioteca só recusa escopo SEM TTL (seria inócuo); com TTL ela aceita `public` sem um
    # aviso sequer. Medir isso é o que transforma "tome cuidado" em "o freio é este gate".
    publico = FastMCP("cache-público-descartável", tools=[], cache_ttl=60, cache_scope="public")
    escopos = {h.scope for h in _hints_do_servidor(publico).values()}
    check(
        f"a biblioteca aceita `cache_scope='public'` sem erro nem aviso (escopos: {sorted(escopos)}) "
        "— o freio contra compartilhar entre identidades é ESTE gate, não ela",
        escopos == {"public"},
    )

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        print(
            "   Se a intenção foi LIGAR cache: leia o topo deste arquivo. O que falta responder "
            "não é o escopo — é o que acontece com a trilha (ADR-023) de `resources/read`."
        )
        return 1
    print("\n✅ nenhum hint de cache sai deste servidor — a recusa da Fase 5 está travada.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
