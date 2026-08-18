"""A fórmula Agent Assisted Hours reproduz o exemplo que a Microsoft publica.

POR QUE ISTO É GATE. A AAH foi adotada para trocar premissa nossa por premissa citável de
terceiro. Esse ganho só existe enquanto a implementação AINDA FOR a fórmula deles — e uma fórmula
implementada à mão deriva calada: muda um peso, troca um arredondamento, alguém "melhora" a
atribuição de desfecho, e o painel continua dizendo "Agent Assisted Hours (Microsoft)" com o
crachá de outro sobre a conta da casa. Não há como um teste de tipo pegar isso.

O exemplo é o publicado em learn.microsoft.com/microsoft-copilot-studio/guidance/
agent-business-value-measure-impact, com os números dele:

    10.000 sessões; 5.000 citam pelo menos uma fonte, média de 2 referências = 10.000 referências
    das 5.000 sem referência: 3.000 resolvem, 2.000 escalam ou abandonam
    ponderadas = 3.000 × 1.0 + 2.000 × 0.7          = 4.400
    AAH        = (10.000 + 4.400) × 6 ÷ 60          = 1.440 h
    valor      = 1.440 × 72                          = US$ 103.680

O caso já pegou um erro real: a primeira versão prorrateava a taxa de escalação uniformemente
sobre as sessões sem referência e devolvia 4.700 ponderadas — mais generoso que a fórmula que
diz implementar, no único lugar do sistema onde ser generoso é fabricar resultado.
"""

from __future__ import annotations

import sys

from app.modules.usecases.internal.outcomes import outcomes
from app.modules.usecases.internal.value_model import assumption as premissa_default


def _rodar(*, conversas, com_refs, referencias, escalados, hora):
    """Roda `outcomes` com os agregados do exemplo, sem tocar em store nem em Foundry."""
    import app.modules.conversations.public as conversas_pub
    import app.modules.tickets.public as tickets_pub
    from app.shared.telemetry import cost

    conversas_pub.usage_totals = lambda agent="": {  # type: ignore[assignment]
        "conversations": conversas,
        "input_tokens": 0,
        "output_tokens": 0,
        "references": referencias,
        "conversations_with_references": com_refs,
    }
    tickets_pub.list_tickets = lambda **kw: [None] * escalados  # type: ignore[assignment]
    # Sem tokens não há custo, então o preço não interfere; fixar em zero mantém o teste sobre a
    # AAH e não sobre a tabela de preços, que muda por outros motivos.
    cost.price_for = lambda modelo: (0.0, 0.0)  # type: ignore[assignment]
    cost.usd_brl = lambda: 1.0  # type: ignore[assignment]

    return outcomes(
        {"id": "exemplo", "agents": []},
        {**premissa_default(), "hourly_cost": hora, "currency": "USD"},
    )


def main() -> int:
    r = _rodar(
        conversas=10_000, com_refs=5_000, referencias=10_000, escalados=2_000, hora=72.0
    )

    esperado = {
        "references": 10_000,
        "sessions_without_references": 5_000,
        "weighted_sessions": 4_400.0,
        "assisted_hours": 1_440.0,
        "assisted_value": 103_680.0,
    }
    falhas = [
        f"  {campo}: {r.get(campo)!r} — a Microsoft publica {valor!r}"
        for campo, valor in esperado.items()
        if r.get(campo) != valor
    ]

    # O multiplicador e os pesos são DA FÓRMULA, não da premissa da empresa. Se alguém os tornar
    # editáveis, o número deixa de ser comparável com o de qualquer outra instalação.
    # As constantes agora moram em `value/default.yaml`. O gate segue cobrando os valores
    # PUBLICADOS — tornar o modelo declarativo não pode virar porta para editar a fórmula da
    # Microsoft e continuar chamando o número de Agent Assisted Hours.
    padrao = premissa_default()
    if padrao["minutes_per_reference"] != 6.0:
        falhas.append("  multiplicador default deixou de ser 6 min (o publicado pela Microsoft)")
    if (padrao["resolved_weight"], padrao["unresolved_weight"]) != (1.0, 0.7):
        falhas.append("  pesos de desfecho deixaram de ser 1.0 / 0.7 (os publicados)")

    # ── O MODELO É DADO, e o dado não pode destravar a fórmula ────────────────────────────
    import os
    import tempfile

    from app.modules.usecases.internal import value_model

    doc = value_model.load()
    if doc.get("schema") != "foundry-assured/value-model/v1":
        falhas.append("  o documento perdeu a marca de schema")
    # A procedência tem de vir junto com o número: multiplicador da Microsoft, hora nossa.
    proc = value_model.provenance()
    if "microsoft" not in proc.get("multiplier_source", "").lower():
        falhas.append("  a procedência do multiplicador deixou de citar a fonte da Microsoft")
    if not proc.get("formula_doc", "").startswith("https://learn.microsoft.com"):
        falhas.append("  o link da fórmula publicada sumiu da procedência")

    # `VALUE_MODEL` aponta para outro documento — é como uma instalação usa o modelo dela sem
    # fork. E um documento adulterado NÃO consegue mexer nos pesos da fórmula publicada: eles
    # moram em código de propósito, porque valor travado dentro do arquivo editável não é travado.
    with tempfile.NamedTemporaryFile("w", suffix=".yaml", delete=False) as f:
        f.write(
            "schema: foundry-assured/value-model/v1\n"
            "constants:\n"
            "  minutes_per_reference: {value: 30.0, source: local}\n"
            "  hourly_cost: {value: 500.0, currency: BRL, source: local}\n"
            "  resolved_weight: {value: 9.9}\n"
            "  unresolved_weight: {value: 9.9}\n"
        )
        alternativo = f.name
    anterior = os.environ.get("VALUE_MODEL")
    try:
        os.environ["VALUE_MODEL"] = alternativo
        outro = value_model.assumption()
        if (outro["minutes_per_reference"], outro["hourly_cost"]) != (30.0, 500.0):
            falhas.append("  VALUE_MODEL não trocou a premissa — instalação não consegue a sua")
        if (outro["resolved_weight"], outro["unresolved_weight"]) != (1.0, 0.7):
            falhas.append(
                "  um documento conseguiu mexer nos pesos da fórmula publicada — a partir daí o "
                "número não é mais Agent Assisted Hours, mas continuaria dizendo que é"
            )
    finally:
        if anterior is None:
            os.environ.pop("VALUE_MODEL", None)
        else:
            os.environ["VALUE_MODEL"] = anterior
        os.unlink(alternativo)

    if falhas:
        print("❌ a implementação divergiu da Agent Assisted Hours publicada:")
        print("\n".join(falhas))
        return 1

    print("✅ Agent Assisted Hours reproduz o exemplo publicado pela Microsoft")
    print(f"   {r['references']} refs + {r['weighted_sessions']} ponderadas"
          f" → {r['assisted_hours']}h → US$ {r['assisted_value']:,.2f}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
