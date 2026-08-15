"""Token and cost accounting, promoted from `wiki_builder` to the shared kernel (Phase 5.5a).

`wiki_builder._CostMeter` computes the number dashboards do not: money. It was scoped to one
CLI run; the same arithmetic is what the serving path needs per domain and, in shared mode,
per tenant for billing and entitlement.

TOKENS are measured exactly (the agent-framework emits gen_ai usage on every model call).
PRICES are editable estimates — confirm them against actual billing before trusting a total.

This module is pure arithmetic over a response object: no OTEL import, no I/O, no global
state. That keeps it testable offline and keeps the shared kernel honest — emitting the
resulting metric is the caller's job.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

# USD per 1M tokens (input, output). Azure/OpenAI list, 2026 — estimates, not billing truth.
PRICE_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5-codex": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
}
DEFAULT_PRICE = (1.25, 10.00)  # conservative fallback for an unknown deployment


def price_for(model: str) -> tuple[float, float]:
    """(input, output) USD per 1M tokens for `model`, longest prefix wins."""
    lowered = model.lower()
    for key in sorted(PRICE_USD_PER_1M, key=len, reverse=True):
        if lowered.startswith(key):
            return PRICE_USD_PER_1M[key]
    return DEFAULT_PRICE


def usage(response) -> tuple[int, int]:
    """(input, output) tokens from a response's gen_ai usage details, 0 when absent."""
    raw = getattr(response, "raw_representation", None)
    details = getattr(raw, "usage_details", None) or {}
    return (
        int(details.get("input_token_count", 0) or 0),
        int(details.get("output_token_count", 0) or 0),
    )


def usd_brl() -> float:
    """Read at call time, not import time, so a test can change it."""
    return float(os.environ.get("USD_BRL", "5.40"))


@dataclass
class CostMeter:
    """Token + cost rollup, fed one agent response at a time."""

    model: str
    input_tokens: int = field(default=0)
    output_tokens: int = field(default=0)
    calls: int = field(default=0)

    def add(self, response) -> None:
        incoming, outgoing = usage(response)
        self.input_tokens += incoming
        self.output_tokens += outgoing
        self.calls += 1

    @property
    def usd(self) -> float:
        price_in, price_out = price_for(self.model)
        return self.input_tokens / 1e6 * price_in + self.output_tokens / 1e6 * price_out

    def report(self) -> str:
        price_in, price_out = price_for(self.model)
        total = self.usd
        return (
            f"💰 Custo ({self.model}, {self.calls} chamadas): "
            f"{self.input_tokens / 1000:.1f}K in + {self.output_tokens / 1000:.1f}K out "
            f"= ${total:.2f} (~R${total * usd_brl():.2f})  "
            f"[preço {price_in}/{price_out} USD/1M · USD_BRL={usd_brl()} — configurável]"
        )
