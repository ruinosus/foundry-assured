"""O Redis configurado e FORA DO AR: a leitura fica de pé, e é a capacidade que cai.

ESTE GATE É OFFLINE E NÃO PRECISA DE DAEMON — de propósito, e é o que o distingue do
`durability_test`. Um Redis que não existe é a coisa mais barata de simular: uma porta fechada em
`127.0.0.1` recusa a conexão na hora, sem rede e sem esperar timeout. O irmão com Redis de
verdade prova a metade positiva (a task sobrevive à réplica); este prova a metade que custava o
servidor inteiro.

O DEFEITO QUE ELE FECHA, medido antes de existir. Com `MCP_REDIS_URL` apontando para um Redis
fora do ar, **as cinco superfícies de leitura respondiam `MCPError: Internal server error`** —
inclusive a busca síncrona, que não usa Redis para nada. E não era a extensão de tasks: era a
LOJA DE SESSÃO. O FastMCP lê o `session_state_store` em TODA requisição, por dentro
(`transforms/visibility.py:316 get_visibility_rules` → `Context.get_state`), então uma
`RedisStore` crua transforma manutenção de cache em servidor fora do ar. O `Basic C0` não tem
réplica, por escolha de SKU: esse cenário é a manutenção normal do recurso, não um acidente.

AS QUATRO PROPRIEDADES:

1. **O gate de boot cobre INDISPONIBILIDADE, não só configuração ausente.** As duas perguntas
   antigas (`MCP_REDIS_URL` vazia, chave de cifra ausente) são sobre o que está escrito; esta é
   sobre o mundo. Sem ela a extensão sobe, o handshake anuncia a capacidade, e a primeira
   submissão volta mascarada.
2. **As cinco superfícies de leitura respondem.** Sobre o servidor real que `main.py` monta,
   pelo dispatch real — que é onde a leitura de sessão acontece.
3. **Prova por mutação: com a loja CRUA a mesma leitura morre.** Sem isto, a propriedade 2 seria
   verde também num servidor que nunca teve o defeito, e ninguém saberia o que o `FallbackWrapper`
   está segurando.
4. **Quem pede task recebe erro que diz o que houve, e o handshake não promete o que não tem.**

    uv run python -m tests.redis_outage_test
"""

from __future__ import annotations

import asyncio
import logging
import sys

from pydantic import SecretStr

#: Uma porta que ninguém escuta, no loopback. Recusa imediata — nada de timeout, nada de rede.
URL_MORTA = "redis://127.0.0.1:6399/0"

#: A cifra do snapshot. Nunca há chave de verdade em repositório (ADR-005); esta existe só para
#: as duas primeiras perguntas de `indisponivel()` saírem do caminho e a terceira ser a testada.
CHAVE_DE_GATE = "gate-outage-" + "z" * 40


def _liga_cifra(valor: str | None) -> None:
    """A chave NO SINGLETON que o pacote lê — ver `tasks_backend.snapshot_cifrado`."""
    from fastmcp_tasks.encryption import clear_codec_cache
    from fastmcp_tasks.settings import tasks_settings

    tasks_settings.encryption_key = SecretStr(valor) if valor else None
    clear_codec_cache()


def _monta():
    """O servidor REAL — o que `main.py` monta, com o mesmo `register_surfaces`."""
    from app.shared.settings import settings
    from mcp_app.auth import build_auth
    from mcp_app.main import build_mcp, register_surfaces, wire_registry

    wire_registry()
    mcp = build_mcp(build_auth(settings.mcp_public_base_url))
    register_surfaces(mcp)
    return mcp


async def _cinco_leituras(mcp) -> dict[str, object]:
    """As cinco superfícies de leitura, pelo dispatch real. Cada valor é o resultado OU o erro."""
    from fastmcp import Client

    from mcp_app import app_evidencias

    async def tenta(rotulo, corotina, resumo):
        try:
            return resumo(await corotina)
        except Exception as exc:  # noqa: BLE001 — o erro É o resultado sob teste
            return f"ERRO {type(exc).__name__}: {str(exc)[:60]}"

    async with Client(mcp) as c:
        return {
            "tools/list": await tenta("t", c.list_tools(), lambda r: sorted(t.name for t in r)),
            "prompts/list": await tenta("p", c.list_prompts(), lambda r: len(r)),
            "resources/list": await tenta("r", c.list_resources(), lambda r: len(r)),
            "resources/read": await tenta(
                "rr", c.read_resource(app_evidencias.URI_RENDERIZADOR),
                lambda r: len(r[0].text or ""),
            ),
            # `show_evidence` é a chamada certa para provar isto: além de atravessar o dispatch
            # (onde a sessão é lida por dentro), ela LÊ a sessão explicitamente. Com o Redis
            # fora, a resposta certa é a tabela vazia — não um erro.
            "tools/call": await tenta(
                "c", c.call_tool("show_evidence", {}),
                lambda r: "vazia"
                if app_evidencias.SEM_BUSCA in f"{r.content}{r.structured_content}"
                else "com linhas",
            ),
        }


async def _uma_leitura(mcp) -> object:
    """`tools/list` e nada mais — a leitura mais barata que atravessa o dispatch inteiro."""
    from fastmcp import Client

    try:
        async with Client(mcp) as c:
            return sorted(t.name for t in await c.list_tools())
    except Exception as exc:  # noqa: BLE001 — o erro É o resultado sob teste
        return f"ERRO {type(exc).__name__}: {str(exc)[:60]}"


async def _pede_task(mcp) -> str:
    """O que um cliente recebe ao insistir em rodar `search_docs` como task.

    O `retrieve` é substituído pelo chamador (ver `main`) porque o desfecho aqui é o servidor
    rodar a chamada SÍNCRONA — isto é, o corpo da tool roda de verdade, e o corpo de verdade iria
    ao Azure AI Search. Este gate é offline; a busca em si não é o que está sob teste.
    """
    from fastmcp import Client
    from fastmcp_tasks import call_tool_task

    async with Client(mcp) as c:
        try:
            tarefa = await asyncio.wait_for(
                call_tool_task(c, "search_docs", {"domain": "techdocs", "query": "x"}),
                timeout=30,
            )
            return f"ACEITOU task {tarefa.task_id[:16]}…"
        except TimeoutError:
            return "TIMEOUT — o cliente ficou pendurado"
        except Exception as exc:  # noqa: BLE001 — o erro É o resultado sob teste
            return f"{type(exc).__name__}: {str(exc)[:150]}"


def _loja_crua():
    """A loja de ANTES: `RedisStore` sem fallback. É a mutação da propriedade 3."""
    from key_value.aio.stores.redis import RedisStore
    from key_value.aio.wrappers.ttl_clamp import TTLClampWrapper

    from mcp_app.sessions import TTL_SEGUNDOS

    return TTLClampWrapper(
        key_value=RedisStore(url=URL_MORTA),
        min_ttl=60,
        max_ttl=TTL_SEGUNDOS,
        missing_ttl=TTL_SEGUNDOS,
    )


def main() -> int:
    from app.shared.settings import settings
    from mcp_app import sessions, tasks_backend, tools_knowledge

    falhas: list[str] = []
    logging.disable(logging.CRITICAL)

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    anterior = (settings.mcp_redis_url, sessions.loja, tools_knowledge.retrieve)
    from fastmcp_tasks.settings import tasks_settings

    chave_anterior = tasks_settings.encryption_key

    async def retrieve_falso(query, user, spec):
        return [{"index": 1, "source": "d.md", "url": "https://x/1", "snippet": "s"}]

    try:
        settings.mcp_redis_url = URL_MORTA
        # Ver `_pede_task`: a chamada acaba rodando síncrona, e o corpo de verdade iria à rede.
        tools_knowledge.retrieve = retrieve_falso
        _liga_cifra(CHAVE_DE_GATE)

        # --- 1 · o gate de boot enxerga o backend fora do ar --------------------------------
        motivo = tasks_backend.indisponivel() or ""
        print(f"     motivo: {motivo[:150]}")
        check(
            "com a URL configurada e o backend fora do ar, as tasks NÃO sobem — a pergunta é "
            "sobre o mundo, não sobre a configuração",
            motivo.startswith(tasks_backend.MOTIVO_BACKEND_FORA[:60]),
        )
        check(
            f"e o motivo leva o erro do `redis-py` junto, para o operador distinguir os casos "
            f"({'ConnectionError' in motivo})",
            "ConnectionError" in motivo,
        )

        from fastmcp.server.providers.base import Provider

        mcp = _monta()
        tools = {t.name: t for t in asyncio.run(Provider.list_tools(mcp))}
        check(
            "a extensão de tasks não foi registrada e `search_docs` nasceu SÍNCRONA",
            "io.modelcontextprotocol/tasks" not in getattr(mcp, "_extensions", {})
            and not tools["search_docs"].task_config.supports_tasks(),
        )

        # --- 2 · as cinco superfícies de leitura respondem ----------------------------------
        leituras = asyncio.run(_cinco_leituras(mcp))
        for metodo, resultado in leituras.items():
            print(f"     {metodo:<16} {resultado}")
        check(
            "as CINCO superfícies de leitura respondem com o Redis fora do ar — nenhuma delas "
            "precisa dele, e a manutenção do Basic C0 (que não tem réplica) não as derruba",
            not any(str(v).startswith("ERRO") for v in leituras.values()),
        )
        check(
            "e a tabela de evidências degrada para VAZIA, que é o que `sessions.py` promete "
            f"perder ({leituras['tools/call']})",
            leituras["tools/call"] == "vazia",
        )

        # --- 3 · prova por mutação: a loja CRUA derruba a MESMA leitura ---------------------
        # UMA superfície basta aqui, e é de propósito: a causa é o dispatch (a leitura interna
        # de sessão), que é a mesma para as cinco — repetir as outras quatro só pagaria quatro
        # vezes os retries do `redis-py` num gate que já é o mais lento deste app.
        sessions.loja = _loja_crua
        cru = asyncio.run(_uma_leitura(_monta()))
        print(f"     com a loja CRUA: {cru}")
        check(
            "com a `RedisStore` CRUA (o que havia antes), a MESMA leitura morre — é o "
            "`FallbackWrapper` que segura, não sorte",
            str(cru).startswith("ERRO"),
        )
        sessions.loja = anterior[1]

        # --- 4 · quem pede task recebe erro que diz o que houve -----------------------------
        resposta = asyncio.run(_pede_task(_monta()))
        print(f"     pedindo task: {resposta}")
        check(
            "quem insiste em task recebe um erro que DIZ que não rodou como task — em vez do "
            f"`Internal server error` mascarado que a extensão no ar devolvia ({resposta[:40]})",
            "did not run as a task" in resposta,
        )
    finally:
        settings.mcp_redis_url, sessions.loja, tools_knowledge.retrieve = anterior
        tasks_settings.encryption_key = chave_anterior
        from fastmcp_tasks.encryption import clear_codec_cache

        clear_codec_cache()
        logging.disable(logging.NOTSET)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ Redis fora do ar derruba a CAPACIDADE de tasks, nunca as leituras.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
