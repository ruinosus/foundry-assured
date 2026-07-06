---
title: "Container Apps (backend + web)"
description: "O plano de controle: backend FastAPI + web Next.js em Azure Container Apps — identidade UserAssigned compartilhada, ingress externo, scale-to-zero, Azure Files para os tickets e o bloco de env vars do backend (Foundry, ACL, selfwiki e os novos artifacts)."
outline: deep
---

# Container Apps (backend + web)

> **Escopo.** `infra/containerapps.bicep` — o segundo módulo compartilhado, composto tanto pelo `main.bicep` (azd) quanto pelo `managedApp.bicep` (stamp dedicado). Provisiona o Container Apps environment e os dois apps (`backend`, `web`) que formam o plano de controle.

## Anatomia

```mermaid
graph TB
  subgraph env["managedEnvironment cae-assured-*"]
    direction TB
    BE["backend<br>ca-backend-*<br>port 8000, min0/max1"]
    WEB["web<br>ca-web-*<br>port 3000, min0/max3"]
    DS["storages 'data'<br>Azure File (tickets)"]
  end
  LA["Log Analytics<br>log-assured-*"]
  ACR["ACR (pull via appIdentity)"]
  UAI["appIdentity (UserAssigned)"]
  env --> LA
  BE -->|volumeMount /app/data| DS
  BE -->|pull| ACR
  WEB -->|pull| ACR
  BE -.identity.-> UAI
  WEB -.identity.-> UAI
  WEB -->|BACKEND_URL/AGUI_URL| BE

  style BE fill:#1e3a5f,stroke:#4a9eed,color:#e0e0e0
  style WEB fill:#1e3a5f,stroke:#4a9eed,color:#e0e0e0
  style DS fill:#2d4a3e,stroke:#4aba8a,color:#e0e0e0
  style LA fill:#5a4a2e,stroke:#d4a84b,color:#e0e0e0
  style ACR fill:#2d2d3d,stroke:#7a7a8a,color:#e0e0e0
  style UAI fill:#2d2d3d,stroke:#7a7a8a,color:#e0e0e0
```

<!-- Sources: infra/containerapps.bicep:70-102, infra/containerapps.bicep:109-227 -->

## O environment e a persistência

O `managedEnvironment` `cae-assured-*` envia logs para o Log Analytics `log-assured-*` (`infra/containerapps.bicep:70-83`). Para os tickets (`tickets.jsonl`) sobreviverem ao scale-to-zero, o módulo monta um **Azure Files** share: referencia a conta de storage `existing` (`infra/containerapps.bicep:87-89`), cria o `storages/data` com a account-key via `listKeys()` (`infra/containerapps.bicep:91-102`) e o monta em `/app/data` no backend (`infra/containerapps.bicep:170-177`).

> **Por que account-key aqui (e não RBAC).** O Azure Files só monta por chave de conta — não há caminho de managed identity para a share key — por isso o `allowSharedKeyAccess: true` da conta (`infra/resources.bicep:194`). O Blob/Table de **artifacts**, ao contrário, é 100% keyless por RBAC ([ver Artifacts](./page-4.md)); a mesma conta serve os dois modelos.

## O app `backend`

Roda como a `appIdentity` UserAssigned (para ACR pull + chamadas keyless a Foundry/Search/artifacts) (`infra/containerapps.bicep:113-116`), com ingress externo na porta 8000 (`infra/containerapps.bicep:121-125`) e o único segredo — o `entra-api-secret` para OBO — via `secretRef`, nunca como env literal (`infra/containerapps.bicep:129-131`, `infra/containerapps.bicep:154`). Escala `min 0 / max 1` porque o `jsonl` é append-based e >1 writer poderia corromper (`infra/containerapps.bicep:178-180`).

### O bloco de env vars do backend

```mermaid
graph LR
  subgraph core["Foundry / Search"]
    E1["FOUNDRY_PROJECT_ENDPOINT"]
    E2["FOUNDRY_MODEL"]
    E3["AZURE_SEARCH_ENDPOINT / _KNOWLEDGE_BASE"]
  end
  subgraph domains["Domínios grounded/tool"]
    E4["SELFWIKI_SEARCH_KNOWLEDGE_BASE"]
    E5["MCP_ENABLED=true"]
  end
  subgraph acl["ACL / OBO"]
    E6["APP_USERS_GROUP_ID"]
    E7["ACL_PUBLIC/INTERNAL/CONFIDENTIAL_GROUP"]
  end
  subgraph art["Artifacts (v0.4.0)"]
    E8["ARTIFACT_STORE_BACKEND=table"]
    E9["ARTIFACT_CONTAINER / _TABLE = artifacts"]
    E10["ARTIFACT_BLOB/STORE_ACCOUNT_URL"]
  end

  style E1 fill:#1e3a5f,stroke:#4a9eed,color:#e0e0e0
  style E2 fill:#1e3a5f,stroke:#4a9eed,color:#e0e0e0
  style E3 fill:#1e3a5f,stroke:#4a9eed,color:#e0e0e0
  style E4 fill:#2d2d3d,stroke:#7a7a8a,color:#e0e0e0
  style E5 fill:#2d2d3d,stroke:#7a7a8a,color:#e0e0e0
  style E6 fill:#5a4a2e,stroke:#d4a84b,color:#e0e0e0
  style E7 fill:#5a4a2e,stroke:#d4a84b,color:#e0e0e0
  style E8 fill:#2d4a3e,stroke:#4aba8a,color:#e0e0e0
  style E9 fill:#2d4a3e,stroke:#4aba8a,color:#e0e0e0
  style E10 fill:#2d4a3e,stroke:#4aba8a,color:#e0e0e0
```

<!-- Sources: infra/containerapps.bicep:139-169 -->

| Grupo | Env vars | Papel | Source |
|---|---|---|---|
| Foundry/Search | `FOUNDRY_PROJECT_ENDPOINT`, `FOUNDRY_MODEL`, `AZURE_SEARCH_ENDPOINT`, `AZURE_SEARCH_KNOWLEDGE_BASE` | conexão base ao Foundry + KB | `infra/containerapps.bicep:140-143` |
| Domínios | `SELFWIKI_SEARCH_KNOWLEDGE_BASE`, `MCP_ENABLED=true` | monta `/selfwiki` + `/platform` | `infra/containerapps.bicep:146-149` |
| Identidade/OBO | `AZURE_CLIENT_ID`, `ENTRA_TENANT_ID`, `ENTRA_API_CLIENT_ID`, `ENTRA_API_CLIENT_SECRET` (secretRef) | DefaultAzureCredential + OBO | `infra/containerapps.bicep:151-154` |
| ACL/audiência **v0.3+** | `APP_USERS_GROUP_ID`, `ACL_PUBLIC_GROUP`, `ACL_INTERNAL_GROUP`, `ACL_CONFIDENTIAL_GROUP` | popula `acl_group_map`; retrieval envia o header ACL por-usuário | `infra/containerapps.bicep:157-162` |
| **Artifacts v0.4.0** | `ARTIFACT_STORE_BACKEND`, `ARTIFACT_CONTAINER`, `ARTIFACT_TABLE`, `ARTIFACT_BLOB_ACCOUNT_URL`, `ARTIFACT_STORE_ACCOUNT_URL` | persistência de HTML gerado (Blob+Table, keyless) | `infra/containerapps.bicep:163-168` |

**Fato (v0.4.0):** o módulo ganhou dois blocos de params novos — os grupos de ACL/app-users (`infra/containerapps.bicep:36-42`) e as URLs de artifact (`infra/containerapps.bicep:50-54`) — e injeta os env correspondentes. O bloco de artifacts está detalhado em [Artifacts](./page-4.md); os grupos ACL deixam os domínios cockpit/selfwiki fail-closed quando vazios (o retrieval só envia o header OBO se o grupo estiver setado).

## O app `web`

O frontend Next.js roda na mesma UAMI, ingress externo na porta 3000 (`infra/containerapps.bicep:185-205`). Recebe os URLs do backend derivados do FQDN previsível do environment — `BACKEND_URL`, `AGUI_URL` (`/helpdesk`), `HOSTED_AGUI_URL` (`/helpdesk-hosted`) e `COCKPIT_AGUI_URL` (`/cockpit`) (`infra/containerapps.bicep:212-221`). Escala `min 0 / max 3` (`infra/containerapps.bicep:224`).

> **Sem referência circular.** Backend e web derivam seus FQDNs do `env.properties.defaultDomain` (criado primeiro), não um do outro (`infra/containerapps.bicep:106-107`) — por isso o web pode apontar para o backend sem um ciclo de dependência.

O módulo exporta os FQDNs públicos como `BACKEND_URL` / `WEB_URL` (`infra/containerapps.bicep:229-230`).

## Related Pages

| Página | Relação |
|---|---|
| [Recursos Compartilhados](./page-3.md) | a UAMI, a conta de storage e os outputs consumidos aqui |
| [Artifacts — Storage Privado + RBAC](./page-4.md) | o detalhe dos cinco env vars de artifact |
| [O Stack azd](./page-2.md) | o `main.bicep` que passa os params a este módulo |
| [Stamp Dedicado + Lighthouse](./page-6.md) | o outro veículo que compõe este mesmo módulo |
