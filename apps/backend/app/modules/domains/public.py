"""Superfície do módulo `domains`. Único ponto importável de fora (ADR-017).

Os DOIS composition roots consomem daqui — `app/registry.py` (que monta as rotas do monolito) e
`apps/mcp/mcp_app/main.py` (que serve a tool `search_docs`). É o ponto inteiro da extração: os
dois precisam da MESMA lista de domínios, e enquanto ela morava dentro de `app/registry.py` o
segundo tinha que importar a composição do primeiro.
"""

from __future__ import annotations

from app.modules.domains.internal.catalog import (
    DOMAIN_KINDS,
    DomainSpec,
    domain_spec,
    domain_specs,
)

__all__ = ["DOMAIN_KINDS", "DomainSpec", "domain_spec", "domain_specs"]
