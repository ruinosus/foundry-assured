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

# USD por 1M tokens (entrada, saída), para deployment GLOBAL.
#
# ISTO É RESERVA, NÃO FONTE. A fonte é a Azure — `app/modules/pricing`, que lê a API pública
# `prices.azure.com`. Esta tabela existe para o caso sem rede, e cada linha dela foi CONFERIDA
# contra o catálogo real (meter `GPT 5 Mini Inpt Glbl 1M Tokens` = 0.25, etc.): as cinco batem.
#
# O defeito nunca foi o preço — era o CASAMENTO. `price_for` casava por prefixo mais longo, então
# `gpt-5-pro` casava com a linha de `gpt-5` (subestimando 12×) e `gpt-4.1-nano` com a de `gpt-4.1`
# (superestimando 20×). Nenhum dos dois chegava ao "fallback conservador": variante nova casa
# antes, e erra calada. Agora o casamento é EXATO depois de tirar o sufixo de versão, e modelo
# desconhecido devolve None — que a tela mostra como "não sei", não como um número.
PRICE_USD_PER_1M: dict[str, tuple[float, float]] = {
    "gpt-5-codex": (1.25, 10.00),
    "gpt-5-mini": (0.25, 2.00),
    "gpt-5": (1.25, 10.00),
    "gpt-4.1-mini": (0.40, 1.60),
    "gpt-4.1": (2.00, 8.00),
    "gpt-4.1-nano": (0.10, 0.40),
    "gpt-5-pro": (15.00, 120.00),
}


def _sem_versao(model: str) -> str:
    """O nome do modelo sem o sufixo de VERSÃO do deployment (`gpt-5-mini-2026-08-01`).

    Nomear deployment com a data é padrão da Azure, e era o caso legítimo que o casamento por
    prefixo resolvia — de quebra abrindo o ilegítimo. Só o sufixo FINAL, e nunca até esvaziar:
    `gpt-5` não pode virar string vazia, que casaria com qualquer coisa.

    A regra vive DUAS vezes: aqui e em `app/modules/pricing`. Não é descuido — o shared kernel não
    pode importar módulo de negócio (ADR-017), e a de lá casa 1.455 meters da Azure enquanto esta
    casa cinco linhas. São trabalhos diferentes; o que não pode divergir são os RESULTADOS, e
    `tests/pricing/azure_prices_test.py` compara os dois lado a lado.
    """
    partes = [p for p in model.lower().split("-") if p]
    cauda: list[str] = []
    while partes and partes[-1].isdigit():
        cauda.insert(0, partes.pop())
    # Só corta se a cauda numérica contiver um ANO (4 dígitos). `gpt-5-mini-2026-08-01` corta;
    # `gpt-5` não, porque ali o "5" é a geração do modelo, não a versão do deployment — e cortá-lo
    # transformaria o nome em "gpt", que não é modelo nenhum. Foi o erro da primeira versão desta
    # regra, e ele só apareceu porque o teste cobre `gpt-5` puro.
    if not any(len(p) >= 4 for p in cauda):
        partes.extend(cauda)
    return "-".join(partes)


def price_for(model: str) -> tuple[float, float] | None:
    """(entrada, saída) USD por 1M tokens, ou **None** quando o modelo não é conhecido.

    `None` em vez de um default: um preço inventado para um modelo que não está na tabela é
    indistinguível de um preço real na tela, e foi assim que `gpt-5-pro` passaria por um modelo
    12× mais barato. Quem chama decide o que mostrar — e a resposta certa é "não sei".
    """
    return PRICE_USD_PER_1M.get(_sem_versao(model))


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
    def usd(self) -> float | None:
        """O custo, ou None quando o preço do modelo é desconhecido — nunca um zero enganoso."""
        preco = price_for(self.model)
        if preco is None:
            return None
        return self.input_tokens / 1e6 * preco[0] + self.output_tokens / 1e6 * preco[1]

    def report(self) -> str:
        tokens = (
            f"{self.input_tokens / 1000:.1f}K in + {self.output_tokens / 1000:.1f}K out"
        )
        preco, total = price_for(self.model), self.usd
        if preco is None or total is None:
            # Dizer que não sabe o preço é informação; imprimir R$ 0,00 seria uma medida falsa.
            return (
                f"💰 Tokens ({self.model}, {self.calls} chamadas): {tokens} — preço deste "
                f"modelo não está na tabela de reserva; consulte app/modules/pricing."
            )
        return (
            f"💰 Custo ({self.model}, {self.calls} chamadas): {tokens} "
            f"= ${total:.2f} (~R${total * usd_brl():.2f})  "
            f"[preço {preco[0]}/{preco[1]} USD/1M · USD_BRL={usd_brl()} — configurável]"
        )
