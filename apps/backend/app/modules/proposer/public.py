"""Superfície do propositor. Único ponto importável de fora (ADR-017).

Note o que NÃO está aqui: nada que publique. É a ADR-022 na forma de módulo — o propositor
rascunha (Path A) e mostra a otimização do Foundry (Path B); publicar e promover continuam sendo
as rotas de escrita já existentes, com o papel Admin.
"""

from __future__ import annotations

from app.modules.proposer.internal.changeset import (
    build_changeset_proposal,
    review_changeset_proposal,
)
from app.modules.proposer.internal.draft import (
    build_prompt,
    catalog_snapshot,
    parse_draft,
    propose_agent,
)
from app.modules.proposer.internal.optimize import (
    get_optimization,
    list_optimizations,
    start_optimization,
)

__all__ = [
    "build_changeset_proposal",
    "build_prompt",
    "catalog_snapshot",
    "get_optimization",
    "list_optimizations",
    "parse_draft",
    "propose_agent",
    "review_changeset_proposal",
    "start_optimization",
]
