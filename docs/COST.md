---
title: Cost — what Foundry Assured costs, and how the number is derived
description: Total Azure cost of the stack from the Bicep, the Microsoft-indicated way to compute it (Retail Prices API + Azure Cost Estimator), with live SKU prices, the always-on floor, and the per-deployment-mode model (self_hosted / dedicated / shared).
type: reference
audience: operator
status: stable
updated: 2026-06-30
---

# Cost

**Bottom line:** one data plane has an always-on floor of **≈ $79/month (~$0.11/hour)**, and
**~93% of it is Azure AI Search Basic** ($73.73/mo). Everything else is usage-based and **≈ $0
while idle** (the Container Apps scale to zero, Log Analytics stays inside the free tier, storage is
pennies). Left running with light demo use it's **~$80–90/month**; `azd down` drops it to ~$0 (a few
cents of retained storage). The one meter to watch is **AI Search** — it has no scale-to-zero, so the
control is `azd down`, not downsizing (Basic is the floor for agentic retrieval).

> **Multi-tenant note (SaaS):** that ≈ $79/mo floor is **per data plane**. The number below is the
> single-stack cost; the [per-deployment-mode model](#cost-per-deployment-mode) shows how it maps to
> `self_hosted` (one stack you run), `dedicated` (one stack in the **customer's** subscription via the
> Managed App), and `shared` (one shared control plane + per-tenant data-plane resources). The
> SaaS evolution (sub-projects A→B→C→D) added **no new always-on SKU** — the dedicated stamp reuses
> the same Bicep modules, Azure Lighthouse delegation is free, and the 3rd hosted agent is consumption.

## How this number is derived (the Microsoft-indicated method)

Three official ways to cost an `azd`/Bicep stack — this doc uses the second, and is reproducible
with the third:

1. **[Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/)** — manual, web,
   good for a per-region sanity check.
2. **[Azure Retail Prices API](https://learn.microsoft.com/rest/api/cost-management/retail-prices/azure-retail-prices)**
   (`https://prices.azure.com/api/retail/prices`) — public, no-auth, programmatic. **Every fixed
   price in the table below was pulled live from this API** (USD, `eastus2`). Example:

   ```bash
   curl -s "https://prices.azure.com/api/retail/prices?\$filter=serviceName%20eq%20'Azure%20Cognitive%20Search'%20and%20armRegionName%20eq%20'eastus2'%20and%20skuName%20eq%20'Basic'"
   # → "retailPrice": 0.101, "unitOfMeasure": "1 Hour", "meterName": "Basic Unit"
   ```

3. **[ACE — Azure Cost Estimator](https://github.com/TheCloudTheory/arm-estimator)**
   (`dotnet tool install -g azure-cost-estimator`) — the IaC-native tool: it compiles
   `bicep build → ARM` and queries that same Retail Prices API per resource, producing the whole
   estimate automatically. To reproduce this doc end-to-end:

   ```bash
   az bicep build --file infra/main.bicep --outfile /tmp/main.json
   azure-cost-estimator /tmp/main.json <subscriptionId> rg-<env> \
     --inline location=eastus2 environmentName=<env>     # ACE reads SKUs from the ARM, prices via the API
   ```

## What the Bicep provisions (billable)

From [`infra/resources.bicep`](../infra/resources.bicep) + [`infra/containerapps.bicep`](../infra/containerapps.bicep):
a Foundry (Cognitive Services `AIServices` **S0**) account + project, **gpt-5-mini** +
**text-embedding-3-small** deployments (both `GlobalStandard`, pay-per-token), **Azure AI Search
Basic**, **Storage** `Standard_LRS` (corpus blobs + a 1 GiB file share for `tickets.jsonl`),
**Log Analytics** `PerGB2018` + Application Insights, **Container Registry Basic**, a **Container
Apps** environment with 2 apps (backend `min 0/max 1`, web `min 0/max 3`, both scale-to-zero), and
**3 Foundry hosted agents** (`helpdesk-concierge`, `cockpit-expert`, `platform-concierge`, 0.5 vCPU /
1 GiB each — the 3rd, platform, is the D-packaging Invocations twin). Managed identity, role
assignments, connections, blob containers and the file service are free.

The **dedicated stamp** ([`infra/managed-app/managedApp.bicep`](../infra/managed-app/managedApp.bicep))
**composes the same `resources.bicep` + `containerapps.bicep` modules** — so a dedicated tenant's cost
is this same stack, billed to the *customer's* subscription. **Azure Lighthouse**
([`infra/lighthouse/`](../infra/lighthouse/)) is a delegation (`Microsoft.ManagedServices`) with **no
resource cost**, and the Managed Application wrapper itself carries no Azure fee beyond the resources
in its `mainTemplate.json`.

## Cost table (live Retail-API prices, `eastus2`, USD)

| Resource | SKU | List price (Retail API) | Monthly (730 h) | Type |
|---|---|---|---|---|
| **Azure AI Search** | Basic | **$0.101 / hr** | **≈ $73.73** | 🔴 **fixed / always-on — the meter to watch** |
| **Container Registry** | Basic | $0.1666 / day | ≈ $5.07 | 🔴 fixed / always-on |
| Azure AI Foundry | Cognitive Services S0 | $0 platform fee | $0 | 🟢 pay-per-token (below) |
| Container Apps (backend + web) | Consumption, 0.5 vCPU / 1 GiB, scale-to-zero | vCPU $0.000024/s · mem $0.000003/GiB-s · req $0.40/1M | ≈ $0 idle¹ | 🟢 usage |
| Log Analytics / App Insights | PerGB2018 | $2.30 / GB analyzed (first 5 GB/mo free) | ≈ $0 demo² | 🟡 usage |
| Blob storage (corpus) | Hot LRS | $0.0184 / GB-mo | < $0.05 | 🟢 usage |
| Azure Files (tickets) | Standard LRS, 1 GiB | $0.0255 / GB-mo | ≈ $0.03 | 🟢 usage |
| Model — gpt-5-mini | GlobalStandard | ~$0.25 in / ~$2.00 out per 1M tok³ | pennies / session | 🟢 usage |
| Embeddings — text-embedding-3-small | GlobalStandard | ~$0.02 per 1M tok³ | cents / re-ingest | 🟢 usage |
| Foundry hosted agents ×3 | Agent Service | compute + token-based⁴ | variable | 🟢 usage |

¹ Both apps set `minReplicas: 0` → idle = $0; demo traffic falls inside the monthly free grant
(180k vCPU-s + 360k GiB-s + 2M requests). ² Demo tracing stays well under the 5 GB/mo free tier.
³ **Published Foundry-model list price — not yet surfaced by the Retail Prices API**, so treat as
reference, not a live quote. ⁴ Foundry Agent Service hosted agents bill the underlying model tokens
+ container compute; only accrues while invoked (deprovisions ~15 min after the last call). This is
the least-pinned-down line.

## Cost per deployment mode

The same Bicep serves three `DEPLOYMENT_MODE`s (ADR-007); the cost model differs by **who pays** and
**what's shared**. The floor below is the single-data-plane number from the table above.

| Mode | What's deployed | Always-on floor | Who pays | Delivery vehicle |
|---|---|---|---|---|
| **`self_hosted`** | one full stack (the `azd` deployment) | ≈ **$79/mo** | you (the operator) | `azd up` |
| **`dedicated`** | one full stack **in the customer's subscription** | ≈ **$79/mo** *(on the customer's bill)* | the **customer** | Azure **Managed Application** ([`infra/managed-app/`](../infra/managed-app/)) — you operate, they pay |
| **`shared`** | one shared control plane + **per-tenant data plane** (each tenant's own Foundry project / AI Search via their `Connection` records) | ≈ **$79/mo × active data planes** + a flat control plane | per the SaaS operator's pricing; data-plane resources are the customer's (BYO, [ADR-004](./adr/ADR-004-byo-data-plane-foundry-project.md)) | shared multi-tenant app + Azure **Lighthouse** for cross-tenant management |

Key points:
- **AI Search Basic is the floor in every mode** — there's one per data plane and it has no
  scale-to-zero. In `shared`, a tenant's AI Search lives in *their* Foundry project (BYO data plane),
  so it's the tenant's cost, not the platform's.
- **`dedicated` and `shared` add no platform-side always-on SKU.** Lighthouse is free; the Managed
  App wrapper is free; the 3rd hosted agent is consumption. The control plane (the backend + web
  Container Apps) scales to zero.
- **The reproducible per-resource estimate** (the [official method](#how-this-number-is-derived-the-microsoft-indicated-method) above) runs identically against
  the dedicated stamp: `az bicep build --file infra/managed-app/managedApp.bicep` → the same Retail
  Prices API / ACE pass, since it composes the same modules.

## Teardown

```bash
azd ai agent delete helpdesk-concierge   # remove just a hosted agent
azd down --purge                         # delete the whole resource group (stops the AI Search meter)
```

See [DEPLOYMENT.md → Cost & teardown](./DEPLOYMENT.md#cost--teardown) for where this sits in the
provisioning flow.
