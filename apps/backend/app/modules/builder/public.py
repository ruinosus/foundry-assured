"""Superfície do módulo builder. Único ponto importável de fora (ADR-017).

Duas coisas moram aqui e a separação é proposital: o AGENTE que ajuda a preencher o formulário, e
a MEDIÇÃO do quanto ele ajuda. A segunda existe porque um assistente de tela não aparece em
nenhum caso de uso de negócio — e, sem medição própria, ele seria a única parte do produto que
ninguém sabe se funciona.
"""

from __future__ import annotations

from app.modules.builder.internal.assist_log import (
    DESFECHOS,
    InvalidOutcome,
    record_proposal,
    stats,
)
from app.modules.builder.internal.builder import (
    build_builder_agent,
    builder_agent_proxy,
)

__all__ = [
    "DESFECHOS",
    "InvalidOutcome",
    "build_builder_agent",
    "builder_agent_proxy",
    "record_proposal",
    "stats",
]
