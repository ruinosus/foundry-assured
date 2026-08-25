"""O cenário do `minReplicas: 0`: a réplica morre, e o trabalho e a sessão continuam existindo.

ESTE É O ÚNICO GATE DESTE APP QUE PRECISA DE UM DAEMON, e é por isso que ele mora em job próprio
(`mcp-durable`), como o `mcp-image` faz com o Docker. `scripts/gates.py` promete `DEFAULT_JOBS`
inteiramente offline e determinístico; arrastar um Redis para lá quebraria essa promessa para
todo mundo. O que ele prova, porém, é o que decidiu a compra do recurso — então ele BARRA O
MERGE como os outros (entra em `needs` do `ci-ok`).

O QUE ELE PROVA, E POR QUE OS GATES OFFLINE NÃO CONSEGUEM:

`tests/tasks_backend_test.py` prova a metade negativa — com `memory://`, um processo novo não
acha a task que o anterior aceitou. Essa metade cabe offline porque `memory://` não precisa de
nada. A metade POSITIVA não cabe: só um backend compartilhado de verdade pode mostrar a task
sobrevivendo. O mesmo vale para a sessão.

    tasks    P1 aceita uma task e MORRE ABRUPTAMENTE, dentro da sessão do cliente.
             P2 — interpretador novo, servidor novo, mesmo Redis — pergunta pelo id e a vê
             terminar. É o desligamento por ociosidade, modelado fielmente.

    sessão   P1 grava a evidência sob um principal e morre. P2 lê o mesmo valor, e NÃO lê o de
             outro principal — a durabilidade e o isolamento na mesma medição.

POR QUE P1 MORRE COM `os._exit` DENTRO DA SESSÃO, e não depois de fechá-la. Medido: um
desligamento gracioso deixa o worker CANCELAR a execução em voo, e P2 então lê
`status='cancelled'` — o que faria o gate verde sobre o cenário errado (uma réplica que se
despede não é uma réplica que morre). Matar dentro da sessão dá `working` → `completed`.

`redelivery_timeout` é encurtado para 2s de propósito. O default do Docket é 300s: é o tempo que
o backend espera antes de devolver à fila a execução de um worker que sumiu. Em produção 300s é
o valor certo; num gate, seria cinco minutos de espera para provar a mesma propriedade.

    MCP_REDIS_URL=redis://localhost:6379/0 uv run python -m tests.durability_test
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
import time

#: O nome da fila do Docket neste gate. Separado do de produção para que rodar o gate contra um
#: Redis compartilhado não misture trabalho de verdade com trabalho de teste.
FILA = "gate-durabilidade"

#: O principal de P1 e o de outra pessoa. Strings opacas: o que importa é que são DIFERENTES, e
#: que a `Session` as usa como parede de isolamento (a chave é `sha256(principal)`).
PRINCIPAL = '{"client_id":"cli","issuer":"iss","subject":"ana"}'
OUTRO_PRINCIPAL = '{"client_id":"cli","issuer":"iss","subject":"bruno"}'

#: A cifra do snapshot. Nunca há chave de verdade em repositório (ADR-005); esta existe só para o
#: gate exercitar o caminho CIFRADO, que é o único que produção usa.
CHAVE_DE_GATE = "gate-t7-" + "z" * 40

_PREAMBULO = """
import asyncio, json, os, sys
from datetime import timedelta
from pydantic import SecretStr
from fastmcp import Client, FastMCP
from fastmcp_tasks import TasksExtension, call_tool_task
from fastmcp_tasks.encryption import clear_codec_cache
from fastmcp_tasks.settings import tasks_settings

URL = os.environ["MCP_REDIS_URL"]
tasks_settings.encryption_key = SecretStr(os.environ["GATE_CHAVE"])
clear_codec_cache()

def servidor():
    mcp = FastMCP("durabilidade", tools=[])
    mcp.add_extension(
        TasksExtension(url=URL, name=os.environ["GATE_FILA"],
                       redelivery_timeout=timedelta(seconds=2))
    )

    @mcp.tool(task=True)
    async def lenta(q: str) -> str:
        await asyncio.sleep(2)
        return "pronto:" + q

    return mcp
"""

#: P1 — aceita a task, imprime o id, e MORRE sem teardown. Ver o docstring.
_P1_TASK = _PREAMBULO + """
async def go():
    async with Client(servidor()) as c:
        t = await call_tool_task(c, "lenta", {"q": "abc"})
        st = await t.status()
        print(json.dumps({"task_id": t.task_id, "status": str(st.status)}), flush=True)
        os._exit(0)   # a réplica morre AQUI, dentro da sessão

asyncio.run(go())
"""

#: P2 — processo novo, servidor novo, mesmo Redis. Só tem o id.
_P2_TASK = _PREAMBULO + """
from fastmcp_tasks.client import _send_get   # a rota direta quando só se tem o id

async def go(task_id):
    async with Client(servidor()) as c:
        inicial = await _send_get(c.session, task_id)
        fim = None
        for _ in range(120):
            r = await _send_get(c.session, task_id)
            if str(r.status) not in ("working", "TaskStatus.working"):
                fim = r
                break
            await asyncio.sleep(0.5)
        print(json.dumps({
            "inicial": str(inicial.status),
            "final": str(fim.status) if fim else "TIMEOUT",
            "resultado": str(getattr(fim, "result", ""))[:120],
        }), flush=True)

asyncio.run(go(sys.argv[1]))
"""

_SESSAO = """
import asyncio, json, os, sys
from fastmcp import FastMCP
from fastmcp.server.sessions import Session, _USER_SESSION_ID, session_storage_key

from mcp_app import sessions

async def go(modo, principal):
    # A LOJA REAL do produto (`sessions.loja()`), entregue pelo seam PÚBLICO
    # `FastMCP(session_state_store=...)`. O adaptador que a `Session` recebe é construído pelo
    # FastMCP a partir dela — usar o dele, e não um nosso, é o que faz este gate medir o
    # caminho que o servidor usa, e não um paralelo.
    mcp = FastMCP("durabilidade", tools=[], session_state_store=sessions.loja())
    s = Session(store=mcp._state_store, principal=principal, session_id=_USER_SESSION_ID)
    if modo == "grava":
        await s.set(sessions.CHAVE_EVIDENCIAS,
                    sessions.evidencia_para_guardar("techdocs", [
                        {"index": 1, "source": "runbook-vpn.md", "url": "https://c/x"}]))
        print(json.dumps({"chave": session_storage_key(principal, _USER_SESSION_ID)}), flush=True)
        os._exit(0)
    lido = await s.get(sessions.CHAVE_EVIDENCIAS)
    print(json.dumps({"lido": lido}), flush=True)

asyncio.run(go(sys.argv[1], sys.argv[2]))
"""


def _roda(script: str, *args: str, url: str) -> dict:
    """Roda um dos scripts acima num interpretador NOVO e devolve a última linha JSON dele."""
    ambiente = {
        **os.environ,
        "MCP_REDIS_URL": url,
        "GATE_FILA": FILA,
        "GATE_CHAVE": CHAVE_DE_GATE,
    }
    # `check=False`: um subprocesso que morre é RESULTADO aqui (P1 sai por `os._exit`), não
    # exceção. Quem julga é a asserção, sobre a saída.
    saida = subprocess.run(
        [sys.executable, "-c", script, *args],
        capture_output=True,
        text=True,
        timeout=180,
        env=ambiente,
        check=False,
    )
    linhas = [linha for linha in saida.stdout.splitlines() if linha.startswith("{")]
    if not linhas:
        return {"erro": (saida.stderr or saida.stdout)[-600:]}
    return json.loads(linhas[-1])


def main() -> int:
    url = os.environ.get("MCP_REDIS_URL", "").strip()
    if not url:
        print(
            "❌ este gate PRECISA de um Redis de verdade — é a propriedade dele.\n"
            "   MCP_REDIS_URL=redis://localhost:6379/0 uv run python -m tests.durability_test\n"
            "   No CI ele roda no job `mcp-durable`, que sobe o serviço. Sair verde sem Redis "
            "seria um gate que não prova nada."
        )
        return 1
    if url.startswith("memory://"):
        print("❌ `memory://` é exatamente o que este gate existe para reprovar.")
        return 1

    falhas: list[str] = []

    def check(rotulo: str, condicao: bool) -> None:
        print(f"  {'✅' if condicao else '❌'} {rotulo}")
        if not condicao:
            falhas.append(rotulo)

    # --- 1 · a TASK sobrevive ao processo que a aceitou ---------------------------------
    inicio = time.monotonic()
    p1 = _roda(_P1_TASK, url=url)
    print(f"     P1 aceitou: {p1}")
    check(
        f"P1 aceitou a task e morreu dentro da sessão ({p1.get('erro') or p1.get('status')})",
        bool(p1.get("task_id")),
    )
    if p1.get("task_id"):
        p2 = _roda(_P2_TASK, p1["task_id"], url=url)
        print(f"     P2 (processo novo) viu: {p2} · {time.monotonic() - inicio:.0f}s")
        check(
            "um PROCESSO NOVO acha a task pelo id — o backend durável é o que sustenta a "
            f"promessa de TTL que o servidor fez ao cliente ({p2.get('inicial')})",
            p2.get("inicial") in ("working", "TaskStatus.working", "completed"),
        )
        check(
            f"e ela TERMINA nesse processo novo ({p2.get('final')}) — o worker da réplica nova "
            "recebe de volta o trabalho da que morreu",
            "completed" in str(p2.get("final")),
        )
        check(
            f"com o resultado da tool intacto ({str(p2.get('resultado'))[:48]})",
            "pronto:abc" in str(p2.get("resultado")),
        )

    # --- 2 · a SESSÃO sobrevive, e não atravessa entre pessoas ---------------------------
    gravou = _roda(_SESSAO, "grava", PRINCIPAL, url=url)
    print(f"     P1 gravou em: {str(gravou.get('chave'))[:56]}…")
    check("P1 gravou a evidência e morreu", bool(gravou.get("chave")))

    leu = _roda(_SESSAO, "le", PRINCIPAL, url=url)
    check(
        f"um PROCESSO NOVO lê a evidência do mesmo principal ({str(leu.get('lido'))[:60]})",
        isinstance(leu.get("lido"), dict)
        and leu["lido"].get("sources", [{}])[0].get("source") == "runbook-vpn.md",
    )

    outro = _roda(_SESSAO, "le", OUTRO_PRINCIPAL, url=url)
    check(
        f"e OUTRO principal, no mesmo Redis, não lê nada ({outro.get('lido')!r}) — a parede é "
        "o principal, não o processo",
        outro.get("lido") is None,
    )

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ task e sessão sobrevivem à morte da réplica — o cenário do minReplicas: 0.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
