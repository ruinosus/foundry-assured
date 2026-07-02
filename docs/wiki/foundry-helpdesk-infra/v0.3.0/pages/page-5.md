---
title: "O Stamp Dedicado — Azure Managed Application"
description: "managedApp.bicep re-parametriza os mesmos módulos para a subscription do cliente; createUiDefinition.json + build.sh + mainTemplate.json formam o pacote de marketplace. O caveat de modo Incremental (agora sobre log-assured) e o porquê do principalId vazio."
---

# O Stamp Dedicado — Azure Managed Application

> **Escopo.** [`infra/managed-app/`](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep) — o pacote de **Azure Managed Application** (ADR-002). É a forma de entregar um **control plane dedicado dentro da subscription do cliente**, operado pelo publisher.

## Por que uma Managed Application

ADR-001/ADR-002 decidem que o stamp dedicado (enterprise) seja entregue como Managed Application: o publisher publica o control plane; ele implanta num resource group *gerenciado* dentro da subscription do **cliente**, que o cliente não pode modificar diretamente — "tudo é do cliente", com o publisher como operador ([managedApp.bicep:3-8](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L3-L8)).

## O insight central: re-parametrização, não cópia

A diferença para `main.bicep`:

| Aspecto | `main.bicep` (azd) | `managedApp.bicep` (stamp) | Source |
|---|---|---|---|
| `targetScope` | `subscription` | `resourceGroup` | [main.bicep:10](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/main.bicep#L10) vs [managedApp.bicep:21](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L21) |
| Cria o RG? | Sim (`Microsoft.Resources/resourceGroups`) | **Não** — a plataforma já criou o RG gerenciado | [main.bicep:49-53](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/main.bicep#L49-L53) vs [managedApp.bicep:9-15](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L9-L15) |
| `principalId` para os módulos | `principalId` real | `''` (vazio, intencional) | [main.bicep:62](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/main.bicep#L62) vs [managedApp.bicep:70](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L70) |
| `resourceToken` | `(subscription, env, location)` | `(subscription, resourceGroup().id, location)` | [main.bicep:45](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/main.bicep#L45) vs [managedApp.bicep:45](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L45) |
| Módulos compostos | `resources.bicep` + `containerapps.bicep` | os **mesmos** (`../resources.bicep` + `../containerapps.bicep`) | [main.bicep:55-92](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/main.bicep#L55-L92) vs [managedApp.bicep:64-97](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L64-L97) |

> **Nota v0.3.0:** o `managedApp.bicep` **não** repassa `appUsersGroupId` (nem `principalType`) ao `module resources` — só `location`, `tags`, `resourceToken`, `principalId: ''`, `modelDeploymentName`, `searchLocation` ([managedApp.bicep:64-73](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L64-L73)). Os defaults (`''`) valem, então `appUsersToFoundry` também é pulado no stamp — coerente com o fail-closed. A tag do stamp é `foundry-assured-stamp: managed-app` ([managedApp.bicep:46](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L46)).

```mermaid
graph TB
  subgraph publisher["Tenant do publisher"]
    BUILD["build.sh<br>az bicep build"]
  end
  subgraph package["Pacote marketplace (managed-app.zip)"]
    MT["mainTemplate.json<br>(ARM compilado)"]
    UI["createUiDefinition.json"]
  end
  subgraph customer["Subscription do CLIENTE"]
    MRG["Managed RG<br>(criado pela plataforma)"]
    R["module resources<br>../resources.bicep"]
    A["module apps<br>../containerapps.bicep"]
  end
  MAPP["managedApp.bicep<br>targetScope resourceGroup"]
  MAPP -->|compila| MT
  BUILD --> MT
  BUILD --> UI
  MT -->|deploy Incremental| MRG
  MRG --> R
  MRG --> A
  R --> A

  style BUILD fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style MT fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style UI fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style MRG fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style R fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style A fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
  style MAPP fill:#2d333b,stroke:#6d5dfc,color:#e6edf3
```

<!-- Sources: infra/managed-app/managedApp.bicep:21-97, infra/managed-app/build.sh:19-24 -->

## `principalId` vazio = fail-closed

A escolha mais importante de segurança: `managedApp.bicep` passa `principalId: ''` para o `module resources` ([managedApp.bicep:70](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L70)). Como as role assignments de usuário em `resources.bicep` são condicionais a `if (!empty(principalId))` ([resources.bicep:350-395](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/resources.bicep#L350-L395)), **nenhum grant data-plane de usuário é criado** no stamp. O comentário deixa explícito: no modelo managed-app o publisher opera o stamp, então não se cria grant de usuário — fail-closed por default ([managedApp.bicep:60-63](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L60-L63)).

## O caveat de modo Incremental (NÃO mude para Complete)

Ambos os módulos compostos declaram um Log Analytics com **o mesmo nome** `log-assured-${resourceToken}` ([resources.bicep:140-148](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/resources.bicep#L140-L148), [containerapps.bicep:46-54](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/containerapps.bicep#L46-L54)). Como dois deployments aninhados separados:

- **Modo Incremental** → COMPILA limpo e CONVERGE (ambos implantam o mesmo workspace → idempotente).
- **Modo Complete** → comportamento indefinido / foot-gun ao reconciliar um recurso de nome duplicado declarado por dois módulos.

Conclusão registrada no código: **updates da managed application DEVEM usar Incremental** ([managedApp.bicep:48-57](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L48-L57)).

## O pacote de marketplace

```mermaid
sequenceDiagram
  autonumber
  participant Dev as publisher
  participant Bicep as az bicep build
  participant Zip as zip -j
  participant PC as Partner Center
  Dev->>Bicep: build.sh — compila managedApp.bicep
  Bicep-->>Dev: mainTemplate.json (ARM JSON, committed)
  Dev->>Zip: empacota mainTemplate.json + createUiDefinition.json
  Zip-->>Dev: managed-app.zip (build output, gitignored)
  Dev->>PC: publica o offer (infra-gated)
```

<!-- Sources: infra/managed-app/build.sh:1-27, infra/managed-app/.gitignore:1-3 -->

| Artefato | Papel | Committed? | Source |
|---|---|---|---|
| `managedApp.bicep` | template fonte (Bicep) | sim | [managedApp.bicep:1](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L1) |
| `mainTemplate.json` | root ARM exigido pela Managed App (compilado) | sim | [build.sh:19-20](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/build.sh#L19-L20) |
| `createUiDefinition.json` | wizard do portal (basics + steps) | sim | [createUiDefinition.json:1-91](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/createUiDefinition.json#L1-L91) |
| `build.sh` | compila + zipa o pacote | sim | [build.sh:1-27](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/build.sh#L1-L27) |
| `managed-app.zip` | artefato de marketplace | **gitignored** (mas presente na árvore de trabalho) | [.gitignore:1-3](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/.gitignore#L1-L3) |

O `build.sh` compila `managedApp.bicep → mainTemplate.json` via `az bicep build` ([build.sh:19-20](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/build.sh#L19-L20)) e zipa os dois arquivos *flat* (`zip -j`, sem caminhos de diretório), como o Partner Center exige ([build.sh:22-24](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/build.sh#L22-L24)).

### O wizard (`createUiDefinition.json`)

Expõe ao cliente apenas o essencial: um TextBox `modelDeploymentName` (default `gpt-5-mini`, regex de validação) nos basics ([createUiDefinition.json:6-19](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/createUiDefinition.json#L6-L19)) e um step opcional "Entra OBO" com tenant/clientId (validados como GUID-ou-vazio) e um PasswordBox para o secret ([createUiDefinition.json:20-82](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/createUiDefinition.json#L20-L82)). Os `outputs` casam exatamente com os parâmetros do `managedApp.bicep` ([createUiDefinition.json:83-89](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/createUiDefinition.json#L83-L89)). O wizard **não** pede `principalId` — coerente com o fail-closed acima.

## Outputs do stamp

`managedApp.bicep` exporta os mesmos endpoints do azd, mais um comentário de que servem ao **post-deploy wiring** do publisher (hosted agent + Toolbox), conforme o runbook D-packaging ([managedApp.bicep:99-109](https://github.com/ruinosus/foundry-assured/blob/3333d60d0e9c02b64a532f2c9bad94692cf50075/infra/managed-app/managedApp.bicep#L99-L109)).

## Related Pages

| Página | Relação |
|---|---|
| [Recursos Compartilhados](./page-3.md) | o módulo re-parametrizado aqui; o `if (!empty(principalId))` |
| [Container Apps](./page-4.md) | o outro módulo re-parametrizado; o Log Analytics duplicado |
| [Azure Lighthouse](./page-6.md) | o veículo complementar (shared model) do mesmo ADR-002 |
| [Custo, Parâmetros e Scripts](./page-9.md) | o `build.sh` e o pacote de marketplace |
