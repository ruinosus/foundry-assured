"""O preço por token vem da Azure, e a tabela de reserva não pode discordar dela.

POR QUE ISTO É GATE. `shared/telemetry/cost.py` casava modelo por PREFIXO MAIS LONGO. O efeito
medido contra a lista real da Azure:

    price_for("gpt-5-pro")     -> (1.25, 10.00)   real: (15.00, 120.00)   subestima 12×
    price_for("gpt-4.1-nano")  -> (2.00,  8.00)   real: ( 0.10,   0.40)   superestima 20×

Nenhum dos dois chegava ao `DEFAULT_PRICE` "conservador" do arquivo: variante nova casa com um
prefixo mais curto ANTES, e erra calada. Num painel de ROI, um erro de 12× é o número que alguém
leva para uma reunião.

A fixture é uma CAPTURA REAL de `prices.azure.com` (serviço `Foundry Models`, eastus, 1.455
meters, todas as páginas). O gate roda offline sobre ela — sem rede, sem credencial — e verifica
três coisas:

  1. cada linha da tabela de reserva BATE com o meter correspondente da Azure. É o que a torna
     reserva legítima em vez de chute preservado;
  2. modelo desconhecido devolve `None` nos dois lados — não um preço plausível;
  3. sufixo de versão de deployment (`gpt-5-mini-2026-08-01`) resolve, e nome de OUTRO modelo
     (`gpt-5-pro` contra `gpt-5`) NÃO resolve para o vizinho.

O item 1 é o que justifica a regra de sufixo existir duas vezes (shared kernel não pode importar
módulo de negócio, ADR-017): as implementações podem divergir, os RESULTADOS não.

NOTA SOBRE A FIXTURE. Ela envelhece, e é de propósito que envelheça em silêncio: o teste compara
a tabela CONTRA ela, então uma mudança de preço na Azure não quebra o CI de quem não mexeu em
nada. Para atualizar: `python -m tests.pricing.azure_prices_test --update` (precisa de rede).
"""

from __future__ import annotations

import json
import pathlib
import sys

FIXTURE = pathlib.Path(__file__).with_name("azure_meters_eastus.json")

#: Casos que já apareceram como defeito, com o número real medido na Azure. Cada linha aqui é uma
#: forma concreta de o casamento errar — não um exemplo inventado.
CASOS = (
    ("gpt-5-mini", (0.25, 2.00)),
    ("gpt-5", (1.25, 10.00)),
    ("gpt-5-codex", (1.25, 10.00)),
    ("gpt-4.1", (2.00, 8.00)),
    ("gpt-4.1-mini", (0.40, 1.60)),
    # Os dois que o casamento por prefixo errava, e em direções opostas.
    ("gpt-5-pro", (15.00, 120.00)),
    ("gpt-4.1-nano", (0.10, 0.40)),
)

#: Nome de DEPLOYMENT com sufixo de versão — precisa resolver para o modelo base.
VERSIONADOS = ("gpt-5-mini-2026", "gpt-5-mini-2026-08-01")

#: Nada disto existe. Os dois lados têm de dizer que não sabem.
DESCONHECIDOS = ("llama-9", "claude-3", "")


def _atualizar() -> int:
    import httpx

    filtro = "armRegionName eq 'eastus' and serviceName eq 'Foundry Models'"
    url = f"https://prices.azure.com/api/retail/prices?api-version=2023-01-01-preview&$filter={filtro}"
    itens: list[dict] = []
    while url and len(itens) < 6000:
        corpo = httpx.get(url, timeout=30.0).json()
        itens += [
            {
                "meterName": i["meterName"],
                "retailPrice": i["retailPrice"],
                "unitOfMeasure": i["unitOfMeasure"],
            }
            for i in corpo.get("Items", [])
        ]
        url = corpo.get("NextPageLink")
    FIXTURE.write_text(json.dumps(itens, indent=1) + "\n")
    print(f"✅ fixture regravada: {len(itens)} meters — revise o diff antes de commitar.")
    return 0


def main() -> int:
    if "--update" in sys.argv:
        return _atualizar()

    from app.modules.pricing.public import resolve
    from app.shared.telemetry.cost import PRICE_USD_PER_1M, price_for

    itens = json.loads(FIXTURE.read_text())
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    check(f"a fixture tem catálogo de verdade ({len(itens)} meters)", len(itens) > 1000)

    for modelo, esperado in CASOS:
        azure = resolve(modelo, itens)
        check(f"Azure conhece {modelo} = {esperado}", azure == esperado)
        # Só cobra a reserva quando ela LISTA o modelo: ela é reserva, não catálogo.
        if modelo in PRICE_USD_PER_1M:
            check(f"a reserva concorda com a Azure em {modelo}", price_for(modelo) == azure)

    for nome in VERSIONADOS:
        check(f"{nome} resolve para o modelo base", resolve(nome, itens) == (0.25, 2.00))
        check(f"…e a reserva também resolve {nome}", price_for(nome) == (0.25, 2.00))

    for nome in DESCONHECIDOS:
        check(f"{nome!r} não recebe preço inventado (Azure)", resolve(nome, itens) is None)
        check(f"{nome!r} não recebe preço inventado (reserva)", price_for(nome) is None)

    # O defeito original, dito na forma em que ele existia: um modelo NÃO pode herdar o preço do
    # vizinho de nome mais curto.
    check(
        "gpt-5-pro não herda o preço de gpt-5",
        resolve("gpt-5-pro", itens) != resolve("gpt-5", itens),
    )
    check(
        "gpt-4.1-nano não herda o preço de gpt-4.1",
        resolve("gpt-4.1-nano", itens) != resolve("gpt-4.1", itens),
    )

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) de preço falharam.")
        return 1
    print("\n✅ o preço vem da Azure, a reserva concorda com ela, e desconhecido não vira número.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
