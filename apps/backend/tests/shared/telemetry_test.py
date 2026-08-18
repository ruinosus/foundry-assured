"""Telemetry stays off by default, and content capture is opt-in (Phase 5.5a, I-1 + I-10).

The riskiest thing about adding telemetry to the serving path is that it stops being free:
an exporter nobody asked for, or a prompt in a span attribute. Both are asserted here.

    uv run python -m tests.shared.telemetry_test
"""

from __future__ import annotations

import os
import sys

from app.shared.telemetry import conventions, cost, setup_telemetry
from app.shared.telemetry.content_policy import capture_enabled, redact


class _Settings:
    def __init__(self, capture=False):
        self.telemetry_capture_content = capture


class _Response:
    def __init__(self, incoming, outgoing):
        self.raw_representation = type(
            "raw", (), {"usage_details": {"input_token_count": incoming, "output_token_count": outgoing}}
        )()


def main() -> int:
    failures: list[str] = []

    def check(name: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {name}")
        if not cond:
            failures.append(name)

    # --- Default is no-op: no exporter env → nothing wired, and it must not raise ---
    for var in ("APPLICATIONINSIGHTS_CONNECTION_STRING", "OTEL_EXPORTER_OTLP_ENDPOINT"):
        os.environ.pop(var, None)
    check("no exporter env → setup_telemetry() is a no-op", setup_telemetry() is False)
    check("no-op setup does not mark itself configured", not __import__(
        "app.shared.telemetry", fromlist=["configured"]).configured())

    # --- Content capture is off unless explicitly switched on (I-10) ---
    check("capture off by default", capture_enabled(_Settings()) is False)
    check("capture on when set", capture_enabled(_Settings(True)) is True)

    # --- Redaction catches the credential shapes the policy gate already knows about ---
    check("aws key redacted", "AKIAIOSFODNN7EXAMPLE" not in redact("key AKIAIOSFODNN7EXAMPLE here"))
    check("bearer redacted", "abc.def.ghi" not in redact("Authorization: Bearer abc.def.ghi"))
    check(
        "api-key assignment redacted",
        "hunter2" not in redact("api_key: hunter2"),
    )
    check("ordinary text survives", redact("restart the pod") == "restart the pod")
    long_text = "x" * 5000
    check("long content truncated", len(redact(long_text)) < 2200)

    # --- gen_ai names live in exactly one place ---
    check("conventions expose the gen_ai token attrs", conventions.GEN_AI_USAGE_INPUT_TOKENS
          == "gen_ai.usage.input_tokens")
    check("span_name follows '{operation} {model}'",
          conventions.span_name(conventions.OP_CHAT, "gpt-5-mini") == "chat gpt-5-mini")
    check("span_name without a model is bare", conventions.span_name(conventions.OP_INVOKE_AGENT)
          == "invoke_agent")

    # --- Cost arithmetic: token exato, preço por nome EXATO (não mais por prefixo) ---
    #
    # O casamento por prefixo mais longo saiu daqui. Ele resolvia o caso legítimo (sufixo de
    # versão no nome do deployment) e, com a mesma regra, fazia `gpt-5-pro` herdar o preço de
    # `gpt-5` — 12× menos que o real, medido contra a lista da Azure. Agora o sufixo de VERSÃO é
    # recortado explicitamente e o resto é igualdade; modelo desconhecido não recebe preço.
    # A conferência linha a linha contra a Azure é `tests/pricing/azure_prices_test.py`.
    meter = cost.CostMeter("gpt-5-mini")
    meter.add(_Response(1_000_000, 1_000_000))
    check("tokens accumulate exactly", (meter.input_tokens, meter.output_tokens) == (10**6, 10**6))
    check("gpt-5-mini priced at 0.25 + 2.00", abs(meter.usd - 2.25) < 1e-9)
    check(
        "sufixo de versão do deployment resolve para o modelo base",
        cost.price_for("gpt-5-mini-2026-08-01") == (0.25, 2.00),
    )
    check(
        "…mas OUTRO modelo não herda o preço do vizinho de nome mais curto",
        cost.price_for("gpt-5-pro") == (15.00, 120.00)
        and cost.price_for("gpt-5-nano") is None,
    )
    check("modelo desconhecido não recebe preço", cost.price_for("llama-9") is None)
    check(
        "…e um medidor sem preço não inventa custo zero",
        cost.CostMeter("llama-9").usd is None
        and "não está na tabela" in cost.CostMeter("llama-9").report(),
    )
    check("missing usage counts as zero", cost.usage(object()) == (0, 0))

    if failures:
        print(f"\n❌ {len(failures)} assertion(s) failed.")
        return 1
    print("\n✅ telemetry defaults to off; content capture is opt-in; cost math holds.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
