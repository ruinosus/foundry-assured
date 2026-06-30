---
title: "Sub-projetos SaaS e o runbook de D-packaging"
description: "As specs e plans dos sub-projetos A–D e o runbook infra-gated de packaging — Managed Application, Lighthouse e o agente hosted platform-concierge."
---

# Sub-projetos SaaS e o runbook de D-packaging

## A estrutura superpowers/

A epopeia SaaS é decomposta em quatro sub-projetos (A → D), cada um com sua **spec** (em
`docs/superpowers/specs/`) e seu **plan** de implementação (em `docs/superpowers/plans/`).
A spec de arquitetura-alvo é o topo; cada sub-projeto desce ao detalhe. Esta página
documenta esse conjunto de planejamento e o **D-PACKAGING-RUNBOOK.md** que o operacionaliza.

| Sub-projeto | Spec | Plan |
| --- | --- | --- |
| Arquitetura-alvo | [saas-target-architecture-design.md](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md) | — |
| A — Multitenant foundation | [subproject-a-…-design.md](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-a-multitenant-foundation-design.md) | [plan](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/plans/2026-06-29-subproject-a-multitenant-foundation.md) |
| B — Connections | [subproject-b-…-design.md](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-b-connections-design.md) | [plan](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/plans/2026-06-29-subproject-b-connections.md) |
| C — Credential brokering | [subproject-c-…-design.md](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-c-credential-brokering-design.md) | [plan](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/plans/2026-06-29-subproject-c-credential-brokering.md) |
| D — Runtime | [subproject-d-runtime-design.md](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-runtime-design.md) | [plan](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/plans/2026-06-29-subproject-d-runtime.md) |
| D — Packaging | [subproject-d-packaging-design.md](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md) | [plan](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/plans/2026-06-29-subproject-d-packaging.md) |

> **Convenção de teste (lida em fonte).** O repo usa testes runnable `def main() -> int`
> em `apps/backend/eval/` via `uv run python -m eval.<name>` — **sem pytest**
> ([…subproject-d-packaging.md:9](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/plans/2026-06-29-subproject-d-packaging.md#L9)).
> O plan inteiro é executado por agentes (superpowers), com steps em checkbox
> ([…subproject-d-packaging.md:3](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/plans/2026-06-29-subproject-d-packaging.md#L3)).

## D-packaging — o que ele finaliza

A spec de D-packaging tem três fases, cada uma com um deliverable **infra-free** (autorado
+ validado estruturalmente agora) e uma validação **infra-gated** (Foundry deployado /
Partner Center / tenants de cliente)
([…subproject-d-packaging-design.md:10-12](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md#L10-L12)).

```mermaid
flowchart TB
  subgraph P1["Fase 1 — Hosted platform agent"]
    HP["apps/hosted-platform<br>InvocationsHostServer"]
    BR["stream_platform_agui<br>(AG-UI passthrough)"]
  end
  subgraph P2["Fase 2 — Dedicated stamp IaC"]
    MA["infra/managed-app<br>mainTemplate + createUiDefinition"]
    LH["infra/lighthouse<br>Microsoft.ManagedServices"]
  end
  subgraph P3["Fase 3 — Leftovers"]
    TD["TIER_DOMAINS<br>tier -> domains"]
    PR["collapse PerRequestPlatformAgent"]
    BUG["#3199 write-approval live verify"]
  end
  P1 --> P2 --> P3
  style P1 fill:#161b22,stroke:#30363d,color:#e6edf3
  style P2 fill:#161b22,stroke:#30363d,color:#e6edf3
  style P3 fill:#161b22,stroke:#30363d,color:#e6edf3
  style HP fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style BR fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style MA fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style LH fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style TD fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style PR fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style BUG fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
```
<!-- Sources: docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md:50-152, docs/superpowers/plans/2026-06-29-subproject-d-packaging.md:19-35 -->

### Fase 1 — O agente hosted de paridade total

O agente deployado serve o **mesmo** agente AG-UI de `/platform` com a **mesma governança
da live** (tools por tenant + write-approval HITL). A **inversão crítica**: os
`hosted-agent`/`hosted-cockpit` existentes são variantes *Responses deliberadamente
stripadas* (single-identity, sem OBO/HITL); o `hosted-platform` faz o **oposto** —
serve o mesmo agente AG-UI, mantendo per-tenant + write-approval
([…d-packaging-design.md:70-81](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md#L70-L81)).
Refinamento web-verificado: o "envelope" SSE do Invocations **é o próprio AG-UI** — não há
envelope separado para reverse-engenheirar; a bridge é um proxy passthrough AG-UI
([…d-packaging-design.md:54-67](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md#L54-L67)).
O `stream_platform_agui` real vive em
[apps/backend/app/services/hosted.py](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/backend/app/services/hosted.py);
o container em
[apps/hosted-platform/main.py](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/hosted-platform/main.py).

### Fase 2 — Managed App + Lighthouse como IaC

Autora os artefatos de marketplace agora (validados offline); publish/delegação reais são
infra-gated. **Caminho DRY:** autora o deployment do managed-app em Bicep que **compõe os
módulos `infra/` existentes** (`resources.bicep`, `containerapps.bicep`), depois
`bicep build` → `mainTemplate.json`
([…d-packaging-design.md:109-123](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md#L109-L123)).
O Lighthouse é um registro `Microsoft.ManagedServices` **least-privilege, revogável,
auditável**
([…d-packaging-design.md:119-121](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md#L119-L121)).

### Fase 3 — Leftovers

O mapa `TIER_DOMAINS: dict[str, tuple[str, ...]]` em
[apps/backend/app/core/tenant.py](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/backend/app/core/tenant.py)
fecha a Open Q#3 da ADR-010; `POST /tenant/onboard` aceita um `tier` opcional e semeia
`enabled_domains` ([…d-packaging-design.md:133-140](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md#L133-L140)).
O colapso de `PerRequestPlatformAgent` em `PerRequestAgent` (em
[apps/backend/app/agents/per_request.py](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/backend/app/agents/per_request.py)
e [platform.py](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/apps/backend/app/agents/platform.py))
é refactor puro — **self-hosted byte-identical**
([…d-packaging-design.md:141-145](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md#L141-L145)).

## O runbook — onde a infra entra

O `D-PACKAGING-RUNBOOK.md` é o **veículo dos passos infra-gated** de D-packaging. Um banner
deixa explícito: *"Infra-gated. Every step below requires an external account or a live
Azure subscription/tenant… None of it runs in CI and nothing here has been executed"*
([docs/D-PACKAGING-RUNBOOK.md:3-14](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/D-PACKAGING-RUNBOOK.md#L3-L14)).
Honestidade de scope: nada de "published" fabricado.

| Veículo | Para quê | Artefato | Quem implanta | Fonte |
| --- | --- | --- | --- | --- |
| **Managed Application** | Dedicated stamp (enterprise) | `infra/managed-app/managed-app.zip` | Cliente, do marketplace, na sua subscription | [D-PACKAGING-RUNBOOK.md:22](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/D-PACKAGING-RUNBOOK.md#L22) |
| **Azure Lighthouse** | Gestão de data-plane shared | `infra/lighthouse/lighthouse.bicep` + `parameters.json` | Cliente, delegando escopos ao nosso tenant | [D-PACKAGING-RUNBOOK.md:23](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/D-PACKAGING-RUNBOOK.md#L23) |

```mermaid
sequenceDiagram
  autonumber
  participant PUB as Publisher (nos)
  participant PC as Partner Center
  participant CUST as Cliente
  participant AZ as Subscription do cliente
  PUB->>PC: Step A — build (build.sh) + upload managed-app.zip
  PC-->>PUB: oferta publicada (infra-gated, nao feito aqui)
  CUST->>PC: Step B — abre oferta -> Create
  PC->>AZ: deploy mainTemplate.json (managed RG)
  AZ-->>CUST: BACKEND_URL / WEB_URL
  CUST->>AZ: Step C — delega escopos via Lighthouse (least-privilege)
  PUB->>AZ: Step D — azd deploy platform-concierge + Foundry Toolbox
```
<!-- Sources: docs/D-PACKAGING-RUNBOOK.md:31-176 -->

**Step A — Publish (Partner Center):** `cd infra/managed-app && ./build.sh` →
`mainTemplate.json` + `managed-app.zip`; **deployment mode = Incremental (recommended)** —
**não escolher Complete** (destrutivo: ambos módulos declaram o mesmo Log Analytics
workspace)
([D-PACKAGING-RUNBOOK.md:36-62](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/D-PACKAGING-RUNBOOK.md#L36-L62)).

**Step B — Cliente implanta:** o portal renderiza `createUiDefinition.json`; o cliente
seta `modelDeploymentName` (default `gpt-5-mini`) + campos OBO opcionais. **`principalId`
é vazio no caminho managed-app** — sem grant de data-plane ao usuário deployer,
**fail-closed por padrão**
([D-PACKAGING-RUNBOOK.md:88-99](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/D-PACKAGING-RUNBOOK.md#L88-L99)).

**Step C — Lighthouse:** o cliente delega no escopo de subscription com role set
**least-privilege: Reader + Monitoring Contributor + Log Analytics Reader (sem Owner, sem
Contributor)**; revogação removendo o `registrationAssignments`
([D-PACKAGING-RUNBOOK.md:126-133](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/D-PACKAGING-RUNBOOK.md#L126-L133)).

**Step D — Agente hosted + Toolbox:** o `platform-concierge` carrega write-approval HITL →
usa o protocolo **Invocations** (não Responses); tools resolvem via um **Foundry Toolbox
com OAuth identity passthrough (por tenant, OBO)**
([D-PACKAGING-RUNBOOK.md:146-149](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/D-PACKAGING-RUNBOOK.md#L146-L149)).
`azd deploy platform-concierge` (azd service → `apps/hosted-platform`,
`host: azure.ai.agent`)
([D-PACKAGING-RUNBOOK.md:151-157](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/D-PACKAGING-RUNBOOK.md#L151-L157)).
O mapeamento de tools por conexão é **DADO** — `project_connection_id` por servidor MCP,
OAuth passthrough é dado na conexão (regra #6 / ADR-011)
([D-PACKAGING-RUNBOOK.md:170-176](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/D-PACKAGING-RUNBOOK.md#L170-L176)).

## Validação offline (infra-free)

Antes de qualquer infra: `bicep build` compila o `mainTemplate.json`; **ARM-TTK
(`Test-AzTemplate`)** linta `mainTemplate.json` + `createUiDefinition.json`; o zip monta
no layout de root requerido
([…d-packaging-design.md:125-129](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/superpowers/specs/2026-06-29-subproject-d-packaging-design.md#L125-L129)).
Os artefatos vivem em
[infra/managed-app/](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/infra/managed-app)
e [infra/lighthouse/](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/infra/lighthouse).

## Related Pages

| Página | Relação |
|------|-------------|
| [Arquitetura SaaS multi-tenant](./page-3.md) | A arquitetura que estes sub-projetos implementam |
| [Decisões de arquitetura (ADRs)](./page-4.md) | ADR-002/009/010/011 dirigem D-packaging |
| [Deploy, branching e custo](./page-6.md) | O fluxo de branch e o deploy hosted |
