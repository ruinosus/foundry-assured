---
title: "Decisões de arquitetura (ADRs 001–011)"
description: "As 11 ADRs MADR-style que sustentam a evolução SaaS — tenancy, identidade, segredos, config tenant-scoped, entitlement por domínio e passthrough de Toolbox."
---

# Decisões de arquitetura (ADRs 001–011)

## O que são e por que existem

ADRs capturam decisões de arquitetura significativas: **context → decision →
consequences**, cada uma aterrada na orientação Microsoft que segue. O formato é
leve (MADR-style)
([docs/adr/README.md:1-4](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L1-L4)).
As **11 ADRs compartilham Status: Accepted e Date: 2026-06-29** — todas escritas na mesma
rodada de design SaaS.

O mapeamento spec↔ADR (footer do índice): **ADRs 001–007** pertencem à arquitetura-alvo
SaaS; **ADR-008** refina conexão/segredo para o sub-projeto B; **ADR-009** o credential
brokering + write approval para C; **ADR-010** o entitlement por domínio para D-runtime;
**ADR-011** o passthrough de Toolbox para D-packaging
([docs/adr/README.md:22](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L22)).

## Índice das 11 decisões

| ADR | Decisão (uma linha) | Sub-projeto | Fonte |
| --- | --- | --- | --- |
| 001 | Tenancy = **Deployment Stamps** (híbrido: shared + dedicated) | arch SaaS | [README.md:10](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L10) |
| 002 | Dedicated stamp = **Managed Application**; mgmt cross-tenant = **Lighthouse** | arch SaaS | [README.md:11](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L11) |
| 003 | Identidade = **Entra app multi-tenant**, tenant do `tid`, **OBO** downstream | arch SaaS | [README.md:12](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L12) |
| 004 | Data plane = **BYO por tenant**, Foundry **project** como fronteira de isolamento | arch SaaS | [README.md:13](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L13) |
| 005 | Control plane **nunca armazena segredos do cliente** (passthrough + refs CMK) | arch SaaS | [README.md:14](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L14) |
| 006 | Config **tenant-scoped** — substitui o `settings` global; namespace de memória por tenant | arch SaaS | [README.md:15](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L15) |
| 007 | Coexistência via costura **deployment-mode** (um codebase, três modos) | arch SaaS | [README.md:16](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L16) |
| 008 | **Foundry connections + App Configuration + Key Vault**, não um credential store próprio | B | [README.md:17](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L17) |
| 009 | **Native tool-approval + resolução por Foundry-connection** — sem self-read Key Vault, sem HITL caseiro | C | [README.md:18](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L18) |
| 010 | Domínio por tenant = **license entitlement** no registro do tenant, não feature flag | D-runtime | [README.md:19](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L19) |
| 011 | Resolução de tool hosted = **Foundry Toolbox + OAuth identity passthrough** | D-packaging | [README.md:20](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/README.md#L20) |

## O fio condutor: "não reinvente mecanismos first-party"

A lição que costura 008→011: não reconstruir serviços que a Microsoft já oferece. As
três ADRs de credencial/conexão (008/009/011) convergem nisso, e a 005 é o axioma de
fundo ("não somos um secret store").

```mermaid
graph TD
  A001["ADR-001<br>Deployment Stamps"] --> A007["ADR-007<br>deployment-mode seam"]
  A002["ADR-002<br>Managed App + Lighthouse"] --> A011["ADR-011<br>Foundry Toolbox passthrough"]
  A003["ADR-003<br>Entra multi-tenant + OBO"] --> A005["ADR-005<br>never store secrets"]
  A005 --> A008["ADR-008<br>Foundry connections"]
  A008 --> A009["ADR-009<br>native tool-approval"]
  A009 --> A011
  A006["ADR-006<br>tenant-scoped config"] --> A010["ADR-010<br>domain entitlement"]
  A001 --> A010
  A007 --> A010
  A004["ADR-004<br>BYO data plane"] --> A005
  style A001 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A002 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A003 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A004 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A005 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A006 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A007 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A008 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A009 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A010 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A011 fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
```
<!-- Sources: docs/adr/README.md:22, docs/adr/ADR-008-foundry-connections-app-configuration.md:13, docs/adr/ADR-009-native-tool-approval-foundry-connection-resolution.md:5, docs/adr/ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md:5 -->

## As decisões em detalhe

### ADR-001 — Deployment Stamps híbrido

Adota o padrão **Deployment Stamps** em config híbrida: **shared stamp** (default, SMB),
**dedicated stamp** (enterprise), **self-hosted** (existente). Um stamp é uma cópia
isolada e independente da plataforma; adicionar stamps escala quase-linearmente e contém
o blast radius
([ADR-001:14-26](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-001-tenancy-deployment-stamps.md#L14-L26)).
Consequência: serve SMB e enterprise de uma arquitetura, ao custo de operar múltiplos
tipos de stamp — o que exige a abstração de deployment-mode da ADR-007
([ADR-001:30-33](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-001-tenancy-deployment-stamps.md#L30-L33)).

### ADR-002 — Managed Application + Lighthouse

O dedicated stamp é entregue como **Azure Managed Application** na subscription do
cliente; a gestão de data-plane do modelo shared via **delegação Azure Lighthouse**
([ADR-002:14-22](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-002-dedicated-stamp-managed-app-lighthouse.md#L14-L22)).
Ambos são sancionados pela Microsoft e marketplace-publicáveis; a delegação Lighthouse é
revogável e auditável
([ADR-002:26-29](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-002-dedicated-stamp-managed-app-lighthouse.md#L26-L29)).
Os artefatos são Bicep que compõe os módulos `infra/` existentes, compilados para
`mainTemplate.json` via `bicep build`
([ADR-002:31-39](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-002-dedicated-stamp-managed-app-lighthouse.md#L31-L39)).

### ADR-003 — Identidade multi-tenant + OBO

Converte os app regs API/SPA para **multitenant**; **resolve o tenant do claim `tid`** e
valida `iss`; mantém **OBO** para downstreams de audiência Microsoft, terceiros usam OAuth
passthrough; onboarding = admin consent
([ADR-003:14-24](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-003-multitenant-identity-obo.md#L14-L24)).
Reutiliza a maquinaria OBO existente (`app/core/auth.py`); o risco é que a validação de
token ganha checks obrigatórios `tid`/`iss` + lista de tenants permitidos — um check
faltando é um risco cross-tenant
([ADR-003:27-30](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-003-multitenant-identity-obo.md#L27-L30)).

### ADR-004 — BYO data plane

Cada tenant **traz seu próprio data plane (BYO)**: Foundry project, Search/KB, storage
próprios. *"We never host the customer's models, KB, or data."* O **Foundry project é a
fronteira de isolamento**, um por tenant
([ADR-004:13-21](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-004-byo-data-plane-foundry-project.md#L13-L21)).
Dá a isolação de dados mais forte; o custo é fricção de onboarding para clientes sem
Azure — um tier de data-plane gerenciado fica como opção futura, BYO-first
([ADR-004:24-28](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-004-byo-data-plane-foundry-project.md#L24-L28)).

### ADR-005 — Nunca armazenar segredos

O store guarda **configuração e metadados de conexão apenas — nunca segredos, nunca dado
do cliente**. Audiência Microsoft → OBO cunha token por usuário (nada armazenado);
terceiros (GitHub) → OAuth identity passthrough; segredos em repouso no Key Vault do
cliente, com `Connection.secret_ref` apontando para o URI/connection id, **nunca o valor**
([ADR-005:14-26](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-005-never-store-secrets.md#L14-L26)).
Fato load-bearing: a Microsoft **bloqueia** passar um token de audiência Microsoft a um
endpoint MCP de terceiro — por isso o passthrough OAuth é obrigatório nesse caminho
([ADR-005:27-29](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-005-never-store-secrets.md#L27-L29)).

### ADR-006 — Config tenant-scoped

Substitui o `settings` global por **`TenantConfigProvider.current()`**; faz namespace da
memória por tenant — `memory_scope()` vira `f"{tid}:{user.oid}"` **só na impl
`MultiTenant`** (a `SingleTenant` mantém `user.oid` sem prefixo para não orfanar
memórias); enforça o scoping em **um único choke point**
([ADR-006:16-30](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-006-tenant-scoped-config.md#L16-L30)).
A Microsoft chama o tenant-scoping na camada de dados de "a consideração de segurança mais
importante" para SaaS multitenant; o trade-off é um refactor amplo — cada leitura de
`settings.<x>` deve passar pelo provider, e um scope faltando é um bug de segurança, não
funcional
([ADR-006:9-14](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-006-tenant-scoped-config.md#L9-L14),
[ADR-006:33-36](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-006-tenant-scoped-config.md#L33-L36)).

### ADR-007 — Coexistência {#adr-007-coexistencia}

Um único ponto de variação — **`DEPLOYMENT_MODE`** (env) — seleciona uma impl de
`TenantConfigProvider` no boot: `self_hosted`/`dedicated` → `SingleTenantConfigProvider`,
`shared` → `MultiTenantConfigProvider` resolvendo por `tid`. Disciplina de migração:
**enviar `SingleTenant` primeiro com zero mudança de comportamento** antes de adicionar
`MultiTenant`
([ADR-007:14-31](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-007-coexistence-deployment-mode.md#L14-L31)).
Todo o resto do código pede ao provider "a config do tenant atual" e é **idêntico entre
modos — nunca sabe qual modo roda**
([ADR-007:24-26](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-007-coexistence-deployment-mode.md#L24-L26)).

### ADR-008 — Foundry connections, não credential store próprio

Auth de serviço externo → **Foundry project connections** (a `Connection` guarda um
`foundry_connection_id`, nunca a credencial); config por tenant → **Azure App
Configuration** (prefixo por tenant-id), primeira impl do B é **Azure Table Storage**
(mais barato), swappable; segredos → **Key Vault** via `keyvault_ref`. O B guarda
"**referências e metadados de governança… não credenciais**, e roda **nenhum fluxo
OAuth**"
([ADR-008:16-36](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-008-foundry-connections-app-configuration.md#L16-L36)).
O design anterior fazia o B rodar OAuth e guardar `secret_ref` — o que reinventa dois
serviços first-party e contradiz a ADR-005
([ADR-008:9-14](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-008-foundry-connections-app-configuration.md#L9-L14)).

### ADR-009 — Native tool-approval + resolução por conexão

Resolução de credencial → Foundry connections + OBO; **nunca ler um segredo de Key
Vault**. OBO para servidores de audiência Microsoft; para não-OBO/GitHub via
`Connection.foundry_connection_id` — caminho hosted `get_mcp_tool(project_connection_id=…)`,
caminho interno recupera via `azure-ai-projects` em runtime. `keyvault_ref` é
**deprecado** em favor de `foundry_connection_id`. Write approval → **tool-approval nativo
do framework** via `approval_mode="always_require"`, reusando
`components/chat/TicketApproval.tsx`, exigindo papel **Approver/Admin**
([ADR-009:16-43](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-009-native-tool-approval-foundry-connection-resolution.md#L16-L43)).
Risco aberto: write-approval sobre AG-UI depende do bug agent-framework **#3199** — um
item de verificação com dois checks independentes + fallbacks
([ADR-009:38-43](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-009-native-tool-approval-foundry-connection-resolution.md#L38-L43),
[ADR-009:47-51](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-009-native-tool-approval-foundry-connection-resolution.md#L47-L51)).

### ADR-010 — Domínio por tenant = license entitlement

Modela a habilitação de domínio como **license entitlement no registro do tenant, não
feature flag**: **`TenantRecord.enabled_domains: tuple[str, ...]`** é o entitlement (dado
no catálogo do control plane), lido por uma guarda `require_domain(domain_id)`,
**fail-closed** (sem registro / fora do set → 403). Domínios nomeados: `helpdesk`,
`cockpit`, `selfwiki`, `platform`
([ADR-010:9-27](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-010-per-tenant-domain-entitlement.md#L9-L27)).
Nota de migração: `enabled_domains` defaulta para `()` — registros pré-existentes
deserializam para `()` → **403 em todo domínio até um Admin conceder via
`PUT /tenant/domains`**; backfill recomendado para 403s não serem confundidos com
regressão
([ADR-010:54-62](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-010-per-tenant-domain-entitlement.md#L54-L62)).

### ADR-011 — Foundry Toolbox + OAuth passthrough (hosted)

O agente hosted deployado resolve tools via o **endpoint MCP do Foundry Toolbox** com
**OAuth identity passthrough** — *"The agent never manages credentials."* O container é
**protocol-only** — `apps/hosted-platform` usa `InvocationsHostServer`
(`agent_framework_foundry_hosting`) servindo o mesmo agente AG-UI de `/platform`; o
protocolo Invocations passa o stream AG-UI intocado, então o write-approval sobrevive
([ADR-011:21-37](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md#L21-L37)).
Escolheu o protocolo **Invocations** (não Responses) porque o platform agent carrega
HITL de write-approval que o Responses não consegue round-tripar
([ADR-011:8-19](https://github.com/ruinosus/foundry-assured/blob/feature/saas-d-packaging/docs/adr/ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md#L8-L19)).

## Related Pages

| Página | Relação |
|------|-------------|
| [Arquitetura SaaS multi-tenant](./page-3.md) | A arquitetura que estas ADRs gravam |
| [Sub-projetos e D-packaging](./page-5.md) | Como as ADRs viram código |
| [O mecanismo de assurance](./page-2.md) | O fail-closed que a ADR-010 estende a domínios |
