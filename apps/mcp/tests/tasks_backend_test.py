"""As background tasks: o que vira task, o que as liga, e por que `memory://` não serve.

Este gate é a metade OFFLINE do item. A outra metade — a task sobrevivendo a um processo novo
contra um Redis de verdade — mora em `tests/durability_test.py`, que precisa de daemon e por isso
roda em job próprio (o mesmo arranjo do `mcp-image`).

O QUE ESTE ARQUIVO TRAVA, e por que cada coisa falharia em silêncio sem ele:

1. **O CRITÉRIO, em forma executável.** `search_docs` aceita task; `open_ticket` não. Escrito
   assim, um `task=True` acrescentado à tool de escrita fica vermelho aqui — e a razão de ele
   não poder existir (dois relógios sobre a mesma espera humana) está em `tasks_backend`.
2. **AS DUAS VARIÁVEIS, e a ordem em que elas são cobradas.** Sem backend durável, nada sobe.
   Com backend e sem cifra, também não — e essa segunda metade é a que ninguém adivinharia:
   sem a chave, o snapshot com o access token do chamador iria para o Redis em claro E uma falha
   ao recuperá-lo faria a task rodar SEM identidade nenhuma, com o ACL e a trilha errados.
3. **O EFEITO É MEDIDO NO CODEC, não na variável.** `snapshot_codec()` é o objeto que de fato
   cifra: `PlaintextCodec.protected` é `False`, `EncryptedCodec.protected` é `True`. Perguntar à
   variável de ambiente responderia sobre o ambiente atual enquanto o pacote grava conforme o
   que leu no import — as duas respostas divergem exatamente no caso perigoso.
4. **`memory://` PERDE A TASK ENTRE PROCESSOS.** É a medição que motivou comprar um Redis, e ela
   cabe num gate offline porque `memory://` não precisa de daemon nenhum: submete-se a task neste
   processo, e um SUBPROCESSO — o mesmo interpretador, sem rede — pergunta por ela e não a acha.
   É o modelo fiel do `minReplicas: 0`, o mesmo recurso que `decision_replay_test` já usa.
5. **`task=True` sem a extensão derruba o LIFESPAN, não a chamada.** Medido por mutação, porque
   é o que obriga as duas metades da decisão (registrar a extensão e registrar a tool) a saírem
   do mesmo lugar. Um servidor que sobe e só falha na primeira task seria muito pior.
6. **Não há regressão para quem já usa.** O modo é `optional`: uma chamada comum continua
   síncrona. Se um dia virar `required`, esta linha avisa antes de os clientes descobrirem.

    uv run python -m tests.tasks_backend_test
"""

from __future__ import annotations

import asyncio
import json
import logging
import subprocess
import sys
import textwrap

from pydantic import SecretStr

#: O script do SUBPROCESSO da verificação 4. Monta um servidor com o MESMO `memory://`, e
#: pergunta pela task que o processo pai aceitou. O ponto é que ele é OUTRO PROCESSO: com
#: backend de memória, o estado da task morreu junto com o pai.
_SONDA = textwrap.dedent(
    """
    import asyncio, json, sys
    from fastmcp import FastMCP, Client
    from fastmcp_tasks import TasksExtension
    from fastmcp_tasks.client import _send_get

    async def go(task_id):
        mcp = FastMCP("sonda", tools=[])
        mcp.add_extension(TasksExtension(url="memory://", name="gate-t7"))

        @mcp.tool(task=True)
        async def lenta(q: str) -> str:
            return q

        async with Client(mcp) as c:
            try:
                r = await _send_get(c.session, task_id)
                print(json.dumps({"achou": True, "status": str(r.status)}))
            except Exception as exc:
                print(json.dumps({"achou": False, "erro": type(exc).__name__, "msg": str(exc)}))

    asyncio.run(go(sys.argv[1]))
    """
)


def _liga_cifra(valor: str | None):
    """Ajusta a chave NO SINGLETON que o pacote lê, e derruba o cache do codec.

    `snapshot_codec()` decide sobre `tasks_settings` (avaliado no import do pacote) com um
    `lru_cache` por cima. Mexer em `os.environ` aqui não teria efeito nenhum — e um gate que
    achasse que teve estaria medindo a coisa errada, que é justamente o defeito contra o qual a
    verificação 3 existe.
    """
    from fastmcp_tasks.encryption import clear_codec_cache
    from fastmcp_tasks.settings import tasks_settings

    tasks_settings.encryption_key = SecretStr(valor) if valor else None
    clear_codec_cache()


async def _submete_e_devolve_id() -> str:
    """Aceita uma task neste processo, com `memory://`, e devolve o id que o servidor prometeu."""
    from fastmcp import Client, FastMCP
    from fastmcp_tasks import TasksExtension, call_tool_task

    mcp = FastMCP("pai", tools=[])
    mcp.add_extension(TasksExtension(url="memory://", name="gate-t7"))

    @mcp.tool(task=True)
    async def lenta(q: str) -> str:
        await asyncio.sleep(30)  # nunca termina dentro do gate — o que importa é a ACEITAÇÃO
        return q

    async with Client(mcp) as client:
        tarefa = await call_tool_task(client, "lenta", {"q": "x"})
        return tarefa.task_id


async def _lifespan_cai_sem_extensao() -> str:
    """Registra `task=True` SEM a extensão e tenta conectar. Devolve o texto do erro, ou ''."""
    from fastmcp import Client, FastMCP

    mcp = FastMCP("sem-extensao", tools=[])

    @mcp.tool(task=True)
    async def lenta(q: str) -> str:
        return q

    try:
        async with Client(mcp):
            return ""
    except Exception as exc:  # noqa: BLE001 — o erro É o resultado sob teste
        return f"{type(exc).__name__}: {exc}"


# Gate LINEAR de propósito: a ordem em que as duas variáveis são cobradas É a asserção.
def main() -> int:
    from fastmcp.server.providers.base import Provider

    from app.shared.settings import settings
    from mcp_app import tasks_backend
    from mcp_app.auth import build_auth
    from mcp_app.main import build_mcp, register_surfaces, wire_registry

    falhas: list[str] = []
    logging.disable(logging.CRITICAL)

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    from fastmcp_tasks.settings import tasks_settings

    anterior = (settings.mcp_redis_url, tasks_settings.encryption_key)
    try:
        # --- 2 e 3 · as duas variáveis, cobradas na ordem e medidas no codec ---------------
        settings.mcp_redis_url = ""
        _liga_cifra(None)
        motivo_sem_backend = tasks_backend.indisponivel()
        check(
            f"sem MCP_REDIS_URL as tasks não sobem ({(motivo_sem_backend or '')[:44]}…)",
            motivo_sem_backend == tasks_backend.MOTIVO_SEM_BACKEND,
        )

        # A OUTRA METADE DA MESMA FALTA, e ela existe porque o default do `deployRedis` virou
        # `false`: quem preenche a chave de cifra e não provisiona o Redis não está no modo de
        # repouso — está com uma intenção pela metade, pagando por uma configuração sem efeito.
        # Mesmo desfecho (tasks fora), motivo diferente, e `instalar` o registra como ERROR.
        _liga_cifra("x" * 40)
        motivo_chave_sozinha = tasks_backend.indisponivel()
        check(
            "chave de cifra SEM backend tem motivo próprio — é engano de configuração, não modo "
            f"de repouso ({(motivo_chave_sozinha or '')[:44]}…)",
            motivo_chave_sozinha == tasks_backend.MOTIVO_CHAVE_SEM_BACKEND,
        )
        _liga_cifra(None)

        settings.mcp_redis_url = "memory://"
        motivo_sem_chave = tasks_backend.indisponivel()
        check(
            "com backend e SEM chave de cifra elas continuam não subindo — o snapshot com o "
            "access token do chamador iria em claro, e a task rodaria sem identidade",
            motivo_sem_chave == tasks_backend.MOTIVO_SEM_CHAVE,
        )
        check(
            "e isso é medido no CODEC que grava, não na variável "
            f"(sem chave: protegido={tasks_backend.snapshot_cifrado()})",
            tasks_backend.snapshot_cifrado() is False,
        )

        _liga_cifra("x" * 40)
        check(
            f"com a chave, o codec passa a proteger (protegido={tasks_backend.snapshot_cifrado()}) "
            "e as tasks sobem",
            tasks_backend.snapshot_cifrado() is True
            and tasks_backend.indisponivel() is None,
        )

        # --- 1 e 6 · o critério, e a ausência de regressão ---------------------------------
        wire_registry()
        mcp = build_mcp(build_auth(settings.mcp_public_base_url))
        register_surfaces(mcp)
        tools = {t.name: t for t in asyncio.run(Provider.list_tools(mcp))}
        modos = {
            nome: getattr(getattr(t, "task_config", None), "mode", "sem task_config")
            for nome, t in tools.items()
        }
        print(f"     modos de task: {modos}")
        check(
            "`search_docs` aceita execução em task — é a tool cujo tempo não é nosso "
            f"({modos.get('search_docs')})",
            tools["search_docs"].task_config.supports_tasks(),
        )
        check(
            "`open_ticket` NÃO aceita — quem demora é o humano, e ele já tem a suspensão do "
            f"SEP-2322 ({modos.get('open_ticket')})",
            not tools["open_ticket"].task_config.supports_tasks(),
        )
        check(
            "`show_evidence` NÃO aceita — lê a sessão e devolve; não há chamada remota a esperar "
            f"({modos.get('show_evidence')})",
            not tools["show_evidence"].task_config.supports_tasks(),
        )
        check(
            "o modo é `optional`: uma chamada comum continua SÍNCRONA — quem já usa não muda "
            f"({modos.get('search_docs')})",
            tools["search_docs"].task_config.mode == "optional",
        )

        # --- e o outro lado da mesma decisão: sem as variáveis, a tool nasce sem `task=` ---
        settings.mcp_redis_url = ""
        _liga_cifra(None)
        wire_registry()
        mudo = build_mcp(build_auth(settings.mcp_public_base_url))
        register_surfaces(mudo)
        tools_mudo = {t.name: t for t in asyncio.run(Provider.list_tools(mudo))}
        check(
            "sem as variáveis, `search_docs` nasce SÍNCRONA e a extensão não é registrada — "
            "as duas metades da decisão saem do mesmo lugar",
            not tools_mudo["search_docs"].task_config.supports_tasks()
            and "io.modelcontextprotocol/tasks" not in getattr(mudo, "_extensions", {}),
        )

        # --- 5 · prova por mutação: sem a extensão, cai o LIFESPAN -------------------------
        erro = asyncio.run(_lifespan_cai_sem_extensao())
        print(f"     sem extensão: {erro[:110]}")
        check(
            "`task=True` sem a extensão derruba a CONEXÃO (lifespan), não a chamada — por isso "
            "o registro da tool não pode decidir sozinho",
            "tasks extension" in erro,
        )

        # --- 4 · prova por mutação: `memory://` perde a task entre processos ---------------
        _liga_cifra("x" * 40)
        task_id = asyncio.run(_submete_e_devolve_id())
        # `check=False` porque o resultado sob teste é a SAÍDA da sonda, não o código dela.
        saida = subprocess.run(
            [sys.executable, "-c", _SONDA, task_id],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
        )
        try:
            resposta = json.loads(saida.stdout.strip().splitlines()[-1])
        except (ValueError, IndexError):
            resposta = {"achou": None, "erro": saida.stderr[-400:]}
        print(f"     id aceito: {task_id[:24]}… · processo novo: {resposta}")
        check(
            "com `memory://`, um PROCESSO NOVO não acha a task que o anterior aceitou — o "
            f"modelo fiel do minReplicas: 0 ({resposta.get('erro') or resposta})",
            resposta.get("achou") is False,
        )
    finally:
        settings.mcp_redis_url = anterior[0]
        tasks_settings.encryption_key = anterior[1]
        from fastmcp_tasks.encryption import clear_codec_cache

        clear_codec_cache()
        logging.disable(logging.NOTSET)

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ só a busca vira task, só com backend durável e cifra, e memory:// não serve.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
