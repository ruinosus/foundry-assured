---
title: "Arquitetura SaaS multi-tenant"
description: "A arquitetura-alvo: control plane × data plane, três deployment stamps em um codebase, identidade multi-tenant e isolamento por tenant — documentada na spec de design e nos diagramas saas/."
---

# Arquitetura SaaS multi-tenant

## A evolução, em uma frase

A spec de arquitetura-alvo descreve a transformação do Foundry Assured de um produto
**single-tenant self-hosted** (o cliente provisiona seu próprio Azure via `azd`) em um
**SaaS multi-tenant híbrido** onde **nós somos o orchestrator / control plane** e **todo
dado, compute e credencial fica na nuvem do cliente (BYO)**. Os modelos self-hosted e
managed **coexistem em um codebase — sem fork**
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:20-25).

> **Fato vs. inferência.** O documento é um **design `status: draft`**
> (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:4-6) —
> a arquitetura-alvo, não a implementação completa. Cada sub-projeto A–D tem sua própria
> spec → plan → build. As decisões são gravadas como ADRs 001–011 (ver
> [Decisões de arquitetura](./page-4.md)).

## 1. Control plane × data plane

A divisão de fundo: **nós operamos o control plane** (UI + orchestrator + RBAC + gates
de assurance); todo dado, compute, segredo e conexão vive no **data plane** do cliente. O
store do control plane guarda **config por tenant + metadados de conexão apenas — nunca
segredos, nunca dado do cliente**. Em runtime, resolvemos o tenant do claim `tid` do
token, carregamos a config daquele tenant, cunhamos um token brokered (OBO /
passthrough), e chamamos **o data plane do próprio cliente**. A fronteira natural de
isolamento é o **Foundry project** do cliente
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:39-44).

```mermaid
flowchart TB
  subgraph CP["Control plane — NOSSO (1 instancia)"]
    UI["UI + orchestrator"]
    RBAC["RBAC + assurance gates"]
    STORE["Store por tenant<br>config + refs de conexao<br>NUNCA segredos/dados"]
  end
  subgraph DPA["Data plane — Tenant A (nuvem do cliente)"]
    FA["Foundry project A"]
    KBA["Search/KB A · storage A"]
  end
  subgraph DPB["Data plane — Tenant B (nuvem do cliente)"]
    FB["Foundry project B"]
    KBB["Search/KB B · storage B"]
  end
  UI --> RBAC --> STORE
  STORE -->|"resolve tid -> config + token brokered"| FA
  STORE -->|"resolve tid -> config + token brokered"| FB
  FA --> KBA
  FB --> KBB
  style CP fill:#161b22,stroke:#30363d,color:#e6edf3
  style DPA fill:#161b22,stroke:#30363d,color:#e6edf3
  style DPB fill:#161b22,stroke:#30363d,color:#e6edf3
  style UI fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style RBAC fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style STORE fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style FA fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style KBA fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style FB fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style KBB fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
```
<!-- Sources: docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:39-44, docs/diagrams/saas/01-control-plane-vs-data-plane.mmd -->

## 2. Identidade & fluxo de credencial

| Fase | Mecanismo | Onde a credencial fica | Fonte |
| --- | --- | --- | --- |
| Onboarding (1x/tenant) | admin-consent → service principal + delegação Lighthouse | só config + refs no store | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:52-54) |
| Runtime, audiência Microsoft (Foundry, ADO) | **OBO** — agimos como o usuário, sem passo extra | nenhum segredo armazenado | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:55-57) |
| Runtime, terceiros (GitHub) | **OAuth identity passthrough** — consent por usuário | token no Foundry Agent Service do cliente | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:58-61) |
| Segredos em repouso | Key Vault / CMK do cliente, via `secret_ref` | Key Vault do cliente | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:62-63) |

O caminho OBO **é o `app/core/auth.py` de hoje, tornado multi-tenant**
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:55-57);
implementação atual em
(apps/backend/app/core/auth.py).
A conformância desse padrão OBO (audiência Microsoft) está registrada em
(docs/MICROSOFT-ALIGNMENT.md:29).
O diagrama-fonte:
(docs/diagrams/saas/02-identity-credential-flow.mmd).

## 3. Três deployment stamps — um codebase, três modos

O mesmo código roda em três configurações, diferindo só em **onde o control plane roda**
e **quantos tenants ele serve**
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:71-78).

| Modo | Tenancy | Onde | Veículo | Fonte |
| --- | --- | --- | --- | --- |
| **self-hosted** (hoje) | 1 | nuvem do cliente, cliente opera | `azd up` | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:76) |
| **dedicated** (enterprise) | 1 | nuvem do cliente, nós operamos | Azure **Managed Application** | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:77) |
| **shared** (SMB/default) | N | nossa nuvem | control plane multi-tenant + **Lighthouse** | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:78) |

O **único ponto de variação** é a **costura de resolução de config**: um
`TenantConfigProvider` com impl `SingleTenant` (self-hosted/dedicated — o `settings`
global de hoje) e impl `MultiTenant` (shared — resolve por `tid`). **Todo o resto é
idêntico entre modos**
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:80-83).
O diagrama-fonte:
(docs/diagrams/saas/03-deployment-stamps.mmd).

```mermaid
flowchart TB
  CODE["UM CODEBASE<br>deployment mode = config, nao fork"]
  CODE -->|"shared"| SH["Control plane multi-tenant<br>(1 instancia, N tenants)<br>-.Lighthouse.-> data planes"]
  CODE -->|"dedicated"| DED["Control plane single-tenant<br>via Managed Application<br>(managed RG)"]
  CODE -->|"self_hosted"| SHO["Control plane single-tenant<br>azd up (cliente opera tudo)"]
  style CODE fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style SH fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style DED fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style SHO fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
```
<!-- Sources: docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:71-83, docs/diagrams/saas/03-deployment-stamps.mmd:1-37 -->

O modo é selecionado por um env `DEPLOYMENT_MODE` (default `self_hosted`) que escolhe a
impl do provider no boot — ver
[ADR-007](./page-4.md#adr-007-coexistencia)
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:80-83).
O par Managed Application + Lighthouse tem prova de conformância em
(docs/MICROSOFT-ALIGNMENT.md:62).

## 4. Isolamento por tenant — as três costuras que mudam

O store do control plane guarda, por tenant: um `Tenant` (tier/status), um
`DataPlaneConfig` (ponteiros para Foundry/Search/storage do cliente), `Connection`s
(cada uma com `auth_method` + `secret_ref` que **nunca** é o segredo), e
`DomainAssignment`s (quais agentes habilitados)
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:91-94).
Só **três costuras** mudam no código de hoje; o resto fica intocado:

| Hoje (single-tenant) | Alvo (multi-tenant) | Fonte |
| --- | --- | --- |
| `settings = Settings()` global | `TenantConfigProvider.current()` → config do tenant atual | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:97) |
| `memory_scope()` = `user.oid` | `f"{tid}:{user.oid}"` (namespace por tenant) | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:98) |
| MCP `SERVERS` estático no código | registry estático = catálogo/forma; conexões habilitadas vêm do store por tenant | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:99-100) |

```mermaid
classDiagram
  class Tenant {
    +string tier
    +string status
  }
  class DataPlaneConfig {
    +string foundryProject
    +string search
    +string storage
  }
  class Connection {
    +string auth_method
    +string secret_ref
  }
  class DomainAssignment {
    +string[] enabled_domains
  }
  Tenant "1" --> "1" DataPlaneConfig
  Tenant "1" --> "*" Connection
  Tenant "1" --> "*" DomainAssignment
```
<!-- Sources: docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:91-100, docs/diagrams/saas/04-tenant-config-model.mmd -->

A isolação de dados é **largamente automática** (o dado vive na nuvem do cliente; o
agente chama *o Foundry deles* com o token brokered); o que *nós* isolamos é a config por
tenant + o contexto da requisição em voo, enforçado em **um único choke point de
tenant-scoping**
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:102-104).
A guarda de memória é deliberadamente assimétrica: `SingleTenant` mantém o `user.oid`
**sem prefixo**; só `MultiTenant` prefixa por `tid`, porque chaves de memória são *estado
persistido* — um prefixo silencioso no self-hosted orfanaria memórias existentes
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:118-121).

## 5. Os quatro sub-projetos (A–D)

| Sub-projeto | Foco | Depende de | Fonte |
| --- | --- | --- | --- |
| **A — Multi-tenant foundation** (a espinha) | `TenantConfigProvider` + `DEPLOYMENT_MODE`, Entra multi-tenant, `tid`, store + `memory_scope`; de-risk com `SingleTenant` (zero mudança de comportamento) | — | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:114-123) |
| **B — Connection store + UI** | refs a Foundry connections / Key Vault, `TenantStore` (Table Storage → App Configuration) | A | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:124-131) |
| **C — Credential brokering** | OBO multi-tenant + OAuth passthrough + resolução de `secret_ref` | B | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:132-133) |
| **D — Stamps / packaging** | Managed Application + onboarding Lighthouse | paralelo a B/C | (docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:134-135) |

Convergência: dedicated/self-hosted precisa só de **A→B→C**; o modo shared precisa de
**C ∩ D** (OBO multi-tenant brokerado sobre uma subscription delegada via Lighthouse que
o D provisiona)
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:137-140).
As specs e plans de cada um estão documentados em
[Sub-projetos e D-packaging](./page-5.md). Os plans vivem em
(docs/superpowers/plans/2026-06-29-subproject-a-multitenant-foundation.md).

## Regras fail-closed do controle de acesso

A spec é explícita: tenant não onboarded / config faltando → **nunca cair para outro
tenant**; vazamento cross-tenant → queries tenant-scoped forçadas em **um** choke point
(auditável)
(docs/superpowers/specs/2026-06-29-saas-target-architecture-design.md:142-146).

## Related Pages

| Página | Relação |
|------|-------------|
| [Decisões de arquitetura (ADRs)](./page-4.md) | As 11 decisões que esta arquitetura grava |
| [Sub-projetos e D-packaging](./page-5.md) | As specs/plans + runbook de cada sub-projeto |
| [O mecanismo de assurance](./page-2.md) | As garantias que passam a valer por tenant |
| [Deploy, branching e custo](./page-6.md) | Como os modos se mapeiam a ambientes |
