---
title: "Deploy, branching e custo"
description: "Como provisionar do clone ao deploy (DEPLOYMENT.md), o modelo Git Flow + ambientes (BRANCHING.md) e o custo derivado da Azure Retail Prices API (COST.md)."
---

# Deploy, branching e custo

Esta página cobre o trio operacional: **como rodar** (`DEPLOYMENT.md`), **como o código
flui para produção** (`BRANCHING.md`) e **quanto custa, e como o número é derivado**
(`COST.md`).

## Provisionamento ponta-a-ponta

O `DEPLOYMENT.md` leva do clone fresco a um deploy provisionado e opcionalmente publicado
([docs/DEPLOYMENT.md:2-7](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L2-L7)).
O caminho curto: dois scripts colapsam os passos manuais — após `azd auth login && az
login`, roda-se `azd up`, `./scripts/setup-entra.sh` (opcional), `./scripts/bootstrap.sh`
([DEPLOYMENT.md:20-30](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L20-L30)).
**Pular `setup-entra.sh` roda sem sign-in** (uma única identidade `DefaultAzureCredential`)
([DEPLOYMENT.md:32-33](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L32-L33)).

| Step | O que faz | Fonte |
| --- | --- | --- |
| 1 | `azd up` provisiona infra (Foundry + Search Basic + Storage + ACR + Container Apps) | [DEPLOYMENT.md:63-73](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L63-L73) |
| 2 | Backend `.env` (cola outputs do azd; auth opcional → fallback `DefaultAzureCredential`) | [DEPLOYMENT.md:87-96](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L87-L96) |
| 3 | App regs Entra (SPA + API) + OBO; 3d declara as 4 App Roles | [DEPLOYMENT.md:100-161](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L100-L161) |
| 4 | KB + memory; **três domínios, cada um com seu KB + ingest, implante qualquer subset (≥1)** | [DEPLOYMENT.md:165-196](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L175-L177) |
| 5 | Rodar local (backend `uvicorn`; frontend porta 3000) | [DEPLOYMENT.md:232-240](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L232-L240) |
| 6 | Deploy do agente hosted; **RBAC pós-deploy obrigatório** (senão 403 em runtime) | [DEPLOYMENT.md:244-267](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L244-L267) |
| 7 | Publicar backend + frontend (Container Apps) | [DEPLOYMENT.md:271-288](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L271-L288) |

O Step 3d declara **quatro App Roles — Admin, Author, Approver, Reader** — via
`setup-app-roles.sh`: o **card de aprovação HITL exige Approver ou Admin**; o
`/admin/users` exige Admin
([DEPLOYMENT.md:143-161](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L143-L161)).
O Step 6 alerta: a Managed Identity fresca criada no deploy não pode ser pré-atribuída em
Bicep — precisa de **Azure AI User** + **Search Index Data Reader**, senão o agente
deploya mas retorna **403**
([DEPLOYMENT.md:253-267](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L253-L267)).

## O modelo de branching — Git Flow

O `BRANCHING.md` é o modelo oficial: **Git Flow** — `main` + `develop` long-lived,
`feature/*`, `release/*`, `hotfix/*` short-lived. Mantém **`main` sempre
production-clean** enquanto a feature SaaS multi-tenant (sub-projetos A→D) integra em
`develop`
([docs/BRANCHING.md:12-15](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L12-L15)).
A escolha é deliberada para um time pequeno: a arquitetura é feature-flagged via
`DEPLOYMENT_MODE`, então um move futuro para trunk-based é baixo-risco
([BRANCHING.md:17-20](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L17-L20)).

```mermaid
gitGraph
  commit id: "v0.6.0"
  branch develop
  checkout develop
  commit id: "saas-A"
  branch feature/saas-b
  commit id: "connections"
  checkout develop
  merge feature/saas-b
  branch release/0.7.0
  commit id: "bump"
  checkout main
  merge release/0.7.0 tag: "v0.7.0"
  checkout develop
  merge release/0.7.0
```
<!-- Sources: docs/BRANCHING.md:22-56 -->

| Branch | Vida | Papel | Vem de → vai para | Fonte |
| --- | --- | --- | --- | --- |
| `main` | sempre | Produção, deployable, tag `vX.Y.Z` | ← `release/*`, `hotfix/*` | [BRANCHING.md:24-30](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L24-L30) |
| `develop` | sempre | Integração | ← `feature/*` → `release/*` | [BRANCHING.md:24-30](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L24-L30) |
| `feature/*` | curta | Trabalho de feature | `develop` → `develop` | [BRANCHING.md:24-30](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L24-L30) |
| `release/*` | curta | Estabilização | `develop` → `main` **e** `develop` | [BRANCHING.md:24-30](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L24-L30) |
| `hotfix/*` | curta | Correção em produção | `main` → `main` **e** `develop` | [BRANCHING.md:24-30](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L24-L30) |

**Nunca commitar direto em `main` ou `develop`** — sempre via PR
([BRANCHING.md:32-33](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L32-L33)).
`main` carrega **nada** da epopeia SaaS até um `release/*` cortar de `develop`; gateado por
`DEPLOYMENT_MODE` (default `self_hosted`)
([BRANCHING.md:72-74](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L72-L74)).

Ambientes `azd` nomeados mapeiam aos branches — cada um com seu resource group + data
plane, totalmente isolados
([BRANCHING.md:81-95](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L81-L95)):

| Ambiente | Rastreia | `DEPLOYMENT_MODE` | Fonte |
| --- | --- | --- | --- |
| **dev** | `develop` | `shared` ou `self_hosted` | [BRANCHING.md:81-85](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L81-L85) |
| **staging** | `release/*` | modo prod alvo | [BRANCHING.md:81-85](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L81-L85) |
| **prod** | `main` (tag) | `self_hosted` até SaaS GA | [BRANCHING.md:81-85](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/BRANCHING.md#L81-L85) |

## Custo — o método Microsoft-indicado

O `COST.md` deriva o custo da **Azure Retail Prices API** (`#2`, reproduzível com o ACE
`#3`) — **toda preço fixo da tabela foi puxado live dessa API** (USD, `eastus2`)
([docs/COST.md:21-44](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L21-L44)).
A API é pública, sem auth, programática — ex.:
`"retailPrice": 0.101, "unitOfMeasure": "1 Hour", "meterName": "Basic Unit"` para o Azure
Cognitive Search Basic
([COST.md:26-33](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L26-L33)).

**Bottom line:** o piso always-on é **≈ $79/mês (~$0,11/hora)**, e **~93% disso é o Azure
AI Search Basic ($73,73/mês)** — o resto é usage-based, **≈ $0 enquanto idle**. Com uso de
demo leve, **~$80–90/mês**; `azd down` derruba para ~$0
([COST.md:12-17](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L12-L17)).

| Recurso | Preço (Retail API, eastus2) | Natureza | Fonte |
| --- | --- | --- | --- |
| **Azure AI Search Basic** | $0,101/hr ≈ **$73,73/mês** | fixo/always-on — *the meter to watch* | [COST.md:61](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L61) |
| Container Registry Basic | $0,1666/dia ≈ $5,07 | fixo | [COST.md:62](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L62) |
| Foundry Cognitive Services S0 | $0 platform fee | — | [COST.md:63](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L63) |
| Container Apps | scale-to-zero | ≈ $0 idle | [COST.md:64](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L64) |
| gpt-5-mini GlobalStandard | ~$0,25 in / ~$2,00 out por 1M tok | usage | [COST.md:68](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L68) |
| text-embedding-3-small | ~$0,02 por 1M tok | usage | [COST.md:69](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L69) |

```mermaid
flowchart LR
  RUN["Recursos provisionados<br>(infra/resources.bicep + containerapps.bicep)"] --> API["Azure Retail Prices API<br>prices.azure.com (publica, no-auth)"]
  API --> FIX["Piso fixo: AI Search Basic<br>~$74/mes (93% da conta)"]
  API --> USE["Usage-based<br>tokens · compute · storage = ~$0 idle"]
  FIX --> DOWN["azd down --purge<br>-> ~$0 (para o medidor do Search)"]
  style RUN fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style API fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style FIX fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style USE fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style DOWN fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
```
<!-- Sources: docs/COST.md:46-70, docs/COST.md:79-87 -->

A única alavanca de custo é o **AI Search** — não tem scale-to-zero, então o controle é
`azd down`, não downsizing
([COST.md:12-17](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L12-L17)).
Teardown: `azd ai agent delete helpdesk-concierge` (um agente) ou `azd down --purge` (o RG
inteiro, para o medidor do Search)
([COST.md:81-84](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L81-L84)).

> **Nota de consistência (lida em fonte).** `DEPLOYMENT.md` arredonda o headline do AI
> Search para **~$0,10/hr ≈ $74/mês (~95% da conta)**
> ([DEPLOYMENT.md:340](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/DEPLOYMENT.md#L340)),
> enquanto o `COST.md` cita o preciso **$0,101/hr ≈ $73,73/mês (~93%)**
> ([COST.md:12](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/COST.md#L12)).
> Ambos rastreiam o mesmo `retailPrice: 0.101` da Retail Prices API.

## Related Pages

| Página | Relação |
|------|-------------|
| [Sub-projetos e D-packaging](./page-5.md) | O deploy do agente hosted platform-concierge |
| [Customização e expansão de domínio](./page-7.md) | Os três domínios e o que se troca |
| [O mecanismo de assurance](./page-2.md) | Os gates que rodam no CI antes do deploy |
