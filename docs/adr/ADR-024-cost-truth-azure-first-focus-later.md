# ADR-024 — The price comes from Azure; FOCUS is the reconciliation, and it waits for volume

*Proposed.*

## Context

The ROI panel reports money. Money was the one number in this repository with no source: a
hand-maintained table of USD-per-1M-tokens in the shared kernel, whose own header admitted it was
an estimate. The research question was whether an open-source dataset or specification should
replace it.

Three things were measured, not assumed.

**The table's prices were right; its matching was wrong.** Every one of the five entries matches
Azure's own catalogue meter for meter. But `price_for` matched by *longest prefix*, so any variant
the table does not list inherited the price of the shorter neighbour:

| call | table answered | Azure charges | error |
|---|---|---|---|
| `gpt-5-pro` | 1.25 / 10.00 | **15.00 / 120.00** | 12× understated |
| `gpt-4.1-nano` | 2.00 / 8.00 | **0.10 / 0.40** | 20× overstated |

Neither reached the `DEFAULT_PRICE` the file advertised as a conservative fallback: a new variant
matches a shorter prefix *first*, and is wrong silently. A 12× error is the kind of number someone
carries into a meeting.

**A first-party source already exists.** `prices.azure.com/api/retail/prices` is public and
unauthenticated. Adopting a third-party price dataset (Langfuse, OpenLIT, LiteLLM) would add a
second accounting of the same money to diverge from the first — the failure this repository
already lived once, when `wiki_builder` kept a private copy of the cost table.

**FOCUS is billing truth, not attribution.** The FinOps Open Cost and Usage Specification is at
v1.3 and Azure exports it natively. But its `Tags` attach to Azure *resources*, and one Foundry
project serving four domains is one resource. FOCUS cannot say which use case spent what. It is
not a replacement for telemetry; it is a check on it.

## Decision

**The price comes from the Azure Retail Prices API**, in a `pricing` module of its own — not the
shared kernel, which promises no I/O. The hand table stays as an offline *fallback*, and a gate
compares it against a recorded capture of the real catalogue line by line, which is what makes it
a legitimate fallback rather than a preserved guess.

**An unknown model yields `None`, never a plausible number.** The panel shows "—". Zero and "I
don't know the price" lead to opposite conclusions, and a fabricated conservative price is
indistinguishable from a real one on screen.

**FOCUS is deferred, and the join key is stored now.** `SkuMeter` in the FOCUS export is the same
meter vocabulary the pricing module resolves against. The panel now records which meters a price
came from (`price_meters`), so reconciling estimate against invoice later is a join on data we
already have. Building the ingestion before there is billing volume would mean building something
unverifiable.

## Consequences

- **+** The money number has a first-party source and a gate that says so.
- **+** Three model families the table never listed (`gpt-5-pro`, `gpt-5-nano`, `gpt-4.1-nano`)
  are now priced correctly, and the two families it listed wrongly by inheritance are fixed.
- **+** The meter names make the cost auditable in the same sense the citations make an answer
  auditable — the number points at its source.
- **−** The panel makes a network call for the price. Cached for 24h, and the fallback covers the
  offline case, but it is I/O where there was none.
- **−** Four naming conventions coexist in the Azure catalogue for the same concept, and two
  units (`1K` and `1M`). The matching rules are measured against the catalogue, but a fifth
  convention would need the same treatment.
- **⚠** The recorded catalogue capture ages deliberately: a price change on Azure must not break
  the CI of someone who changed nothing. `--update` refreshes it, and the diff is reviewed.

### The re-evaluation trigger for FOCUS

Build the ingestion when **there is a month of billing with meaningful Foundry spend** — enough
that estimate-versus-invoice divergence would be visible rather than rounding. Until then the
reconciliation would compare two numbers that are both approximately zero.

## References

- [Azure Retail Prices REST API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices)
- [FOCUS cost and usage details schema](https://learn.microsoft.com/azure/cost-management-billing/dataset-schema/cost-usage-details-focus) — `SkuMeter`, `ConsumedQuantity`, `Tags`
- [FinOps Unit Economics capability](https://www.finops.org/framework/capabilities/measure-unit-costs/) — the vocabulary `value/default.yaml` adopts
- [ADR-017](./ADR-017-module-boundaries.md) — why `pricing` is a module and not part of `shared`
