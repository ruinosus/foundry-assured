"""Superfície da trilha de auditoria (ADR-023). Único ponto importável de fora.

O que sai daqui: registrar um evento, ler a trilha, verificar a cadeia, sanear texto antes de
gravá-lo — e RECOLHER o recibo do que foi gravado num bloco (`receipts`), para quem está por
cima poder referenciar o evento sem reler a trilha. O que NÃO sai: nada que apague ou reescreva —
a trilha é append-only por contrato aqui, e por política do Azure no container.
"""

from __future__ import annotations

from collections.abc import Iterator
from contextlib import contextmanager
from contextvars import ContextVar

from app.modules.audit.internal.anchor import (
    AnchorExists,
    build_anchor,
    close_day,
    list_anchors,
)
from app.modules.audit.internal.export import (
    build_package,
    build_report,
    by_conversation,
)
from app.modules.audit.internal.redact import redact
from app.modules.audit.internal.trail import (
    GENESIS,
    KINDS,
    Event,
    InvalidEvent,
    actor,
    actor_detail,
    chain,
    trail,
    verify,
)

#: A caixa da requisição atual, ou `None` quando ninguém está recolhendo — que é o estado
#: normal. `default=None` importa: sem ele, `record()` fora de um `receipts()` estouraria.
_recibos: ContextVar[list[dict] | None] = ContextVar("recibos_da_trilha", default=None)


def record(
    scope: str, actor: str, kind: str, summary: str, ref: str = "", detail: dict | None = None
) -> dict:
    """Grava um evento. Falha NÃO é engolida — ver a nota no chamador.

    Um evento perdido é uma lacuna na cadeia que ninguém detecta, porque a cadeia continua
    consistente sem ele. Por isso quem chama decide o que fazer com o erro: no caminho de
    aprovação, falhar a gravação DEVE impedir a ação (fail-closed, RULE #5).
    """
    if kind not in KINDS:
        raise InvalidEvent(f"tipo de evento desconhecido: {kind!r} (use um de {', '.join(KINDS)})")
    evento = trail().append(scope, actor, kind, summary, ref, detail)
    caixa = _recibos.get()
    if caixa is not None:
        # O ESCOPO VAI JUNTO PORQUE O EVENTO NÃO O CARREGA: `Event` tem seq/at/actor/kind/…, e o
        # escopo é a partição em que ele foi gravado (o arquivo da trilha). Sem ele, um `hash`
        # sozinho não localiza nada — quem for verificar precisa saber em qual trilha procurar.
        caixa.append({"scope": scope, "event": evento})
    return evento


@contextmanager
def receipts() -> Iterator[list[dict]]:
    """Abre uma CAIXA que recolhe os eventos gravados dentro do bloco — o recibo da trilha.

    POR QUE ISTO EXISTE, e por que mora aqui. `record()` sempre devolveu o evento que acabou de
    escrever (com `seq` e `hash`), mas todo chamador o descarta: `retrieval.py` e `document.py`
    gravam dentro de um `suppress(Exception)` e seguem. Quem está POR CIMA da chamada — o selo
    de assurance do MCP, que precisa dizer ao cliente "esta resposta está na trilha, sob este
    id" — não tem como saber o id. Ler a trilha depois para descobrir seria pior de três
    maneiras: baixa o blob inteiro a cada resposta, corre com gravações concorrentes de outro
    processo, e RECALCULA uma informação que já existia. Um selo que recalcula não prova nada.

    O caminho de volta é uma caixa MUTÁVEL posta num ContextVar ANTES da chamada: o valor
    desce para a task do handler (contexto copiado herda a referência) e as anexações sobem,
    porque a lista é a mesma. Medido sobre a mesma pilha ASGI dos gates: o inverso — a callee
    dar `set()` num ContextVar e a caller ler — FUNCIONA quando o corpo da tool é `async`
    (o caso de `search_docs`), mas lê `None` quando o corpo é síncrono, porque aí ele roda numa
    worker thread cujo contexto é CÓPIA — propriedade do `sync`, não do FastMCP. A caixa
    mutável continua sendo a escolha certa por dois motivos: é a única forma que funciona nos
    DOIS casos, e o id teria que sair daqui de qualquer jeito — quem chama `record()` em
    `retrieval.py:107-110` descarta o retorno dentro de um `suppress(Exception)`. Ver
    `apps/mcp/mcp_app/assurance_extension.py`.

    Cada recibo é `{"scope": <partição>, "event": <o evento inteiro, como `record` o devolve>}`.
    Vem INTEIRO de propósito: quem consome escolhe o que expor, e o selo do MCP publica só
    `scope`, `kind` e `hash`, nunca o `detail` (que carrega nome de documento e identidade do
    ator). A regra de não vazar é de quem publica, não desta caixa.

    Reentrante por aninhamento é DE PROPÓSITO não suportado: um bloco interno substitui a caixa
    do externo enquanto dura, e o externo volta a valer depois. Ninguém aninha hoje, e uma
    caixa que se acumulasse em dois níveis faria o selo do nível de fora referenciar eventos
    que não são da resposta dele.
    """
    caixa: list[dict] = []
    token = _recibos.set(caixa)
    try:
        yield caixa
    finally:
        _recibos.reset(token)


def read(scope: str) -> list[dict]:
    """Os eventos de um escopo, na ordem em que foram gravados."""
    return trail().read(scope)


def check(scope: str) -> dict:
    """Reconstrói a cadeia do escopo e diz onde ela quebra, se quebrar."""
    return verify(trail().read(scope))


__all__ = [
    "GENESIS",
    "KINDS",
    "AnchorExists",
    "Event",
    "InvalidEvent",
    "actor",
    "actor_detail",
    "build_anchor",
    "build_package",
    "build_report",
    "by_conversation",
    "chain",
    "check",
    "close_day",
    "list_anchors",
    "read",
    "receipts",
    "record",
    "redact",
    "verify",
]
