"""Superfície do módulo builder. Único ponto importável de fora (ADR-017)."""

from __future__ import annotations

from app.modules.builder.internal.builder import (
    build_builder_agent,
    builder_agent_proxy,
)

__all__ = ["build_builder_agent", "builder_agent_proxy"]
