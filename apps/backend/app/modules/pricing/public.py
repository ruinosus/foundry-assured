"""Preço por token, da fonte de primeira parte. Único ponto importável de fora (ADR-017)."""

from app.modules.pricing.internal.azure_retail import price_for, resolve

__all__ = ["price_for", "resolve"]
