"""FormFlow: os formulários do produto como documento, não como componente.

A única superfície importável deste módulo (ADR-017).
"""

from __future__ import annotations

from app.modules.formflow.internal.loader import (
    FlowInvalid,
    FlowNotFound,
    flows_dir,
    list_flows,
    load_flow,
)

__all__ = ["FlowInvalid", "FlowNotFound", "flows_dir", "list_flows", "load_flow"]
