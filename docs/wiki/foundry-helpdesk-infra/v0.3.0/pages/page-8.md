---
title: "Identidades Entra, ACL e Usuários de Teste"
description: "Como infra/entra/ provisiona os grupos de segurança por classificação (entra.bicep via Microsoft Graph), os scripts portáveis de bootstrap e os dois usuários de teste que provam o trimming de ACL na KB. Inalterado desde a v0.2.0 (ainda com naming 'cockpit')."
---

# Identidades Entra, ACL e Usuários de Teste

> **Escopo.** [`infra/entra/`](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep) — `entra.bicep`, `create-acl-identities.sh`, `create-test-users.sh`, `bicepconfig.json`. É a base do **controle de acesso por documento** na KB. Regra #6 do projeto: controle de acesso é **DADO** (os grupos de leitura de cada fonte), nunca lógica de classificação no código.

> **Nota v0.3.0:** os arquivos de `infra/entra/` **não** mudaram no rename helpdesk→assured — os grupos seguem `SEC-cockpit-kb-*`. O que a v0.3.0 acrescentou é o **grant de grupo** `appUsersToFoundry` em `resources.bicep` (ver [Recursos Compartilhados](./page-3.md)): um grupo de app-users recebe Foundry User para rodar inferência via OBO. Esse grupo é distinto dos três tiers de ACL abaixo.

## Por que grupos por classificação (e não por artefato)

O padrão enterprise least-privilege: em vez de um grupo por documento, os documentos são **classificados por sensibilidade** e cada tier é **um** grupo cloud-only security-enabled. Uma multinacional mapeia esses tiers aos seus próprios; o mapeamento componente→tier vive no pipeline de ingest, então o esquema se adapta sem mexer nas identidades ([entra.bicep:1-8](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep#L1-L8)).

## Os três tiers

```mermaid
graph TB
  PUB["SEC-cockpit-kb-public<br>documentos gerais<br>(todos os funcionários)"]
  INT["SEC-cockpit-kb-internal<br>docs internos de<br>plataforma/componente"]
  CONF["SEC-cockpit-kb-confidential<br>internals de<br>segurança/arquitetura"]

  style PUB fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style INT fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style CONF fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
```

<!-- Sources: infra/entra/entra.bicep:27-52 -->

| Grupo | `uniqueName` | Conteúdo | Source |
|---|---|---|---|
| `SEC-cockpit-kb-public` | `sec-cockpit-kb-public` | público/geral (todos) | [entra.bicep:27-34](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep#L27-L34) |
| `SEC-cockpit-kb-internal` | `sec-cockpit-kb-internal` | plataforma/componente interno | [entra.bicep:36-43](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep#L36-L43) |
| `SEC-cockpit-kb-confidential` | `sec-cockpit-kb-confidential` | segurança/arquitetura | [entra.bicep:45-52](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep#L45-L52) |

Todos são `mailEnabled: false`, `securityEnabled: true` (grupos de segurança cloud-only) ([entra.bicep:31-33](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep#L31-L33)). Os outputs são os object-IDs dos três grupos — alimentam o mapeamento de ACL do ingest (`COCKPIT_ACL_GROUPS`) e o backend ([entra.bicep:54-56](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep#L54-L56)).

## `entra.bicep` via Microsoft Graph (extensão Bicep)

O `entra.bicep` é `targetScope = 'tenant'` e usa a extensão `microsoftGraphV1` para criar objetos de diretório (`Microsoft.Graph/groups@v1.0`) ([entra.bicep:23-25](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep#L23-L25)). A extensão é habilitada em [`bicepconfig.json`](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/bicepconfig.json). A identidade que deploya precisa de direitos de diretório (ex.: Groups Administrator) ([entra.bicep:11-16](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep#L11-L16)).

## A alternativa portável: `create-acl-identities.sh`

**Por que existe um script além do Bicep:** criar objetos de diretório vai pelo Microsoft Graph e precisa de direitos de *diretório* (Groups/User Administrator) — **não** os direitos de ARM tenant-scope que `az deployment tenant create` exige e que contas pessoais/baixo-privilégio não têm. `az ad` chama o Graph direto ([create-acl-identities.sh:2-10](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-acl-identities.sh#L2-L10)).

```mermaid
flowchart TD
  START["./create-acl-identities.sh dominio senha"] --> G{"grupo já existe?"}
  G -->|não| GC["az ad group create"]
  G -->|sim| GR["reusa (idempotente)"]
  GC --> U{"usuário já existe?"}
  GR --> U
  U -->|não| UC["az ad user create<br>force-change-password"]
  U -->|sim| UR["reusa"]
  UC --> M["membership:<br>A em pub+int+conf,<br>B em pub"]
  UR --> M
  M --> OUT["imprime COCKPIT_ACL_*<br>para o backend/.env"]

  style START fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style GC fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style GR fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style UC fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style UR fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style M fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style OUT fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
```

<!-- Sources: infra/entra/create-acl-identities.sh:22-63 -->

É idempotente (re-rodar reusa grupos/usuários) ([create-acl-identities.sh:12](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-acl-identities.sh#L12)). Cria os três grupos ([create-acl-identities.sh:47-49](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-acl-identities.sh#L47-L49)), dois usuários ([create-acl-identities.sh:51-52](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-acl-identities.sh#L51-L52)), faz as memberships e imprime as env vars `COCKPIT_ACL_*` prontas para colar no backend ([create-acl-identities.sh:57-63](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-acl-identities.sh#L57-L63)).

## Os dois usuários de teste — provam o trimming de ACL

`create-test-users.sh` cria exatamente as duas identidades que provam o trimming na hora da query ([create-test-users.sh:2-13](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-test-users.sh#L2-L13)):

| Usuário | Clearance | Deve | Source |
|---|---|---|---|
| **A** (`cockpit-test-a`) | public + internal + confidential | recuperar qualquer doc | [create-test-users.sh:34](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-test-users.sh#L34) |
| **B** (`cockpit-test-b`) | public **apenas** | nunca recuperar um doc confidential | [create-test-users.sh:35](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-test-users.sh#L35) |

A membership reflete isso: A entra nos três grupos, B só no public ([create-test-users.sh:37-38](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-test-users.sh#L37-L38)).

> **Por que usuários ficam num script, não na IaC.** Usuários carregam uma senha inicial, então vivem num script com param seguro, não no Bicep ([create-test-users.sh:8-10](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-test-users.sh#L8-L10)). Ambos nascem com `--force-change-password-next-sign-in true` ([create-test-users.sh:30](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-test-users.sh#L30)).

## Bicep vs script — quando cada um

| | `entra.bicep` | `create-acl-identities.sh` / `create-test-users.sh` |
|---|---|---|
| Mecanismo | extensão Microsoft Graph (IaC) | `az ad` (Graph direto) |
| Direitos exigidos | ARM tenant-scope **+** diretório | só diretório |
| Cria usuários | não (só grupos) | sim (com senha) |
| Indicado para | pipeline org com roles plenas | conta pessoal/dev sem ARM tenant |
| Source | [entra.bicep:11-21](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/entra.bicep#L11-L21) | [create-acl-identities.sh:2-14](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/entra/create-acl-identities.sh#L2-L14) |

> **Não confundir com `scripts/setup-entra.sh`.** Aquele (na pasta `scripts/`) cria as **app registrations** de sign-in/OBO, não os grupos de ACL — ver [Custo, Parâmetros e Scripts](./page-9.md).

## Related Pages

| Página | Relação |
|---|---|
| [Recursos Compartilhados](./page-3.md) | a KB AI Search + o grant `appUsersToFoundry` |
| [Custo, Parâmetros e Scripts](./page-9.md) | referência de `scripts/setup-entra.sh` e os hooks |
| [Hosted Agents](./page-7.md) | o passthrough OAuth (ADR-011), o análogo de entitlement no caminho hosted |
