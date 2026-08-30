"""FormFlow: os formulários do produto como documento, não como componente.

A única superfície importável deste módulo (ADR-017).
"""

from __future__ import annotations

from app.modules.formflow.internal.loader import (
    FlowInvalid,
    FlowNotFound,
    copilots_dir,
    flows_dir,
    list_copilots,
    list_flows,
    load_copilot,
    load_flow,
    verificar_alvos,
)

__all__ = [
    "FlowInvalid",
    "FlowNotFound",
    "copilots_dir",
    "flows_dir",
    "list_copilots",
    "list_flows",
    "load_copilot",
    "load_flow",
    "verificar_alvos",
]
