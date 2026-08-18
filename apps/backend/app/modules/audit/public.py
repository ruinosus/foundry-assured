"""Superfície da trilha de auditoria (ADR-023). Único ponto importável de fora.

O que sai daqui: registrar um evento, ler a trilha, verificar a cadeia, e sanear texto antes de
gravá-lo. O que NÃO sai: nada que apague ou reescreva — a trilha é append-only por contrato aqui,
e por política do Azure no container.
"""

from __future__ import annotations

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
    return trail().append(scope, actor, kind, summary, ref, detail)


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
    "record",
    "redact",
    "verify",
]
