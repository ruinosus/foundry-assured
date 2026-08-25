// Phase 7 (publish): backend + web + mcp on Azure Container Apps. azd builds each image,
// pushes to the ACR, and deploys it to the container app tagged with its
// azd-service-name. All three run as the shared user-assigned identity (created in
// resources.bicep) for ACR pull; the backend and the MCP server also call Foundry + the
// search KB as that identity. The apps reference each other by FQDN derived from the
// environment's defaultDomain, so there's no circular dependency between them.
//
// O `mcp` é uma unidade de deploy PRÓPRIA desde a Fase 0c (ADR-027) — o `/mcp` deixou de ser
// servido pelo backend. Sobre FastMCP 4, num venv que não cabe no do backend: o teto `mcp<2`
// vem do extra `agents` do backend, e o FastMCP 4 exige `mcp>=2,<3`.

@description('Location for all resources.')
param location string

@description('Tags applied to every resource.')
param tags object = {}

@description('Short unique token for resource names.')
param resourceToken string

@description('ACR name (login server is <name>.azurecr.io).')
param registryName string

@description('Resource id of the shared user-assigned identity.')
param appIdentityId string

@description('Client id of the shared user-assigned identity (for DefaultAzureCredential).')
param appIdentityClientId string

// Backend runtime config (mirrors backend/.env).
param foundryProjectEndpoint string
param foundryModel string
param azureSearchEndpoint string
param azureSearchKnowledgeBase string
param entraTenantId string = ''
param entraApiClientId string = ''
@secure()
param entraApiClientSecret string = ''

@description('Entra group of app users — the private read audience of the selfwiki KB. When set, retrieval sends the per-user OBO ACL header for /selfwiki; empty leaves selfwiki fail-closed.')
param appUsersGroupId string = ''

@description('Storage account backing the Azure Files share for persisted app data.')
param storageAccountName string
@description('Blob container do corpus (azd: AZURE_STORAGE_CONTAINER). O backend monta a URL do documento com ele.')
param corpusContainerName string = ''
@description('Resource id da conta de storage (azd: AZURE_STORAGE_RESOURCE_ID).')
param storageResourceId string = ''
@description('Endpoint Azure OpenAI do recurso Foundry (azd: AZURE_AI_OPENAI_ENDPOINT).')
param azureAiOpenAiEndpoint string = ''
@description('Deployment de embedding (azd: FOUNDRY_EMBEDDING_MODEL).')
param embeddingModelName string = ''

@description('Azure Files share mounted into the backend at /app/data (tickets.jsonl).')
param fileShareName string

@description('Azure Files share holding the runtime agent definitions, mounted read-only into the backend at /mnt/agents (ADR-014). Empty share = backend falls back to the definitions baked into the image.')
param promptsShareName string

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var backendAppName = 'ca-backend-${resourceToken}'
var webAppName = 'ca-web-${resourceToken}'
var mcpAppName = 'ca-mcp-${resourceToken}'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-assured-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-assured-${resourceToken}'
  location: location
  tags: tags
  properties: {
    appLogsConfiguration: {
      destination: 'log-analytics'
      logAnalyticsConfiguration: {
        customerId: logAnalytics.properties.customerId
        sharedKey: logAnalytics.listKeys().primarySharedKey
      }
    }
  }
}

// Azure Files persistence for app data (tickets). Files access is account-key only
// (no managed identity for the share key), so we pull it via listKeys.
resource storageAcct 'Microsoft.Storage/storageAccounts@2023-05-01' existing = {
  name: storageAccountName
}

resource envDataStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'data'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAcct.listKeys().keys[0].value
      shareName: fileShareName
      accessMode: 'ReadWrite'
    }
  }
}

// Runtime agent definitions (ADR-014, production leg). Read-only: the runtime
// only READS prompts; publishing goes through scripts/push-prompts.sh (upload
// to the share + revision restart), never through the app.
resource envPromptsStorage 'Microsoft.App/managedEnvironments/storages@2024-03-01' = {
  parent: env
  name: 'prompts'
  properties: {
    azureFile: {
      accountName: storageAccountName
      accountKey: storageAcct.listKeys().keys[0].value
      shareName: promptsShareName
      accessMode: 'ReadOnly'
    }
  }
}

// Predictable external FQDNs from the env's default domain — breaks the
// backend⇄web circular reference (both derive from `env`, created first).
var backendFqdn = '${backendAppName}.${env.properties.defaultDomain}'
var webFqdn = '${webAppName}.${env.properties.defaultDomain}'
var mcpFqdn = '${mcpAppName}.${env.properties.defaultDomain}'

resource backendApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: backendAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'backend' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8000
        transport: 'auto'
      }
      registries: [
        { server: '${registryName}.azurecr.io', identity: appIdentityId }
      ]
      // SÓ declara o segredo quando ELE EXISTE. A Azure recusa um secret sem valor
      // (`ContainerAppSecretInvalid: value or keyVaultUrl and identity should be provided`) e
      // derruba o container app INTEIRO — o backend simplesmente não é criado, enquanto o `web`,
      // que não declara segredo nenhum, sobe normal. O resultado é um resource group com tudo
      // no lugar e um buraco em forma de backend, que não se parece com uma falha de deploy.
      //
      // O caminho PADRÃO do repositório cai exatamente aqui: `up-all.sh` sem `--with-auth` não
      // cria as app registrations, então `entraApiClientSecret` fica `''` — e um clone novo não
      // conseguia subir. Vazio agora significa "sem sign-in", que é um modo suportado.
      secrets: empty(entraApiClientSecret) ? [] : [
        { name: 'entra-api-secret', value: entraApiClientSecret }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1.0Gi' }
          env: concat([
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'FOUNDRY_MODEL', value: foundryModel }
            { name: 'AZURE_SEARCH_ENDPOINT', value: azureSearchEndpoint }
            { name: 'AZURE_SEARCH_KNOWLEDGE_BASE', value: azureSearchKnowledgeBase }
            // selfwiki domain (grounded on this repo's deep-wiki). Setting this mounts /selfwiki;
            // ingest selfwiki-kb so retrieval has data (build_selfwiki_agent tolerates a missing KB at boot).
            { name: 'SELFWIKI_SEARCH_KNOWLEDGE_BASE', value: 'selfwiki-kb' }
            // platform domain (tool-driven, MCP). mcp_enabled defaults false in code, so /platform only
            // mounts when this is true. The first-party MS MCP servers (Learn, etc.) need no extra infra.
            { name: 'MCP_ENABLED', value: 'true' }
            { name: 'FRONTEND_ORIGIN', value: 'https://${webFqdn}' }
            { name: 'AZURE_CLIENT_ID', value: appIdentityClientId }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_API_CLIENT_ID', value: entraApiClientId }
            // `MCP_PUBLIC_BASE_URL` NÃO ENTRA AQUI. Desde a Fase 0c (ADR-027) o backend não serve
            // `/mcp`: quem serve é o container app `mcp` (mais abaixo), e é lá que a variável
            // precisa apontar para o ingress DELE. Deixá-la aqui faria o backend anunciar um
            // recurso OAuth que ele não hospeda.
            // selfwiki audience: the app-users group is the self-wiki's private read audience;
            // retrieval sends the OBO ACL header only when this is set (else /selfwiki fails closed).
            { name: 'APP_USERS_GROUP_ID', value: appUsersGroupId }
            // Runtime agent-definition override (ADR-014, production leg): the
            // backend composes prompts from $AGENTS_DIR/assured when that
            // scope exists on the mounted share, else falls back (loudly) to
            // the copy baked into the image. Prompt update = push-prompts.sh.
            // ── Storage. SEM estes o backend monta `https://.blob.core.windows.net/...`:
            // `/source` filtra o índice por `blob_url eq` e não casa com nada (403 numa citação
            // que o agente acabou de emitir), e o store de conversas não acha container nenhum
            // (lista vazia + 404 em /conversations/by-id). O parâmetro storageAccountName já
            // chegava aqui desde sempre — era usado só para o file share, nunca exposto ao app.
            { name: 'AZURE_STORAGE_ACCOUNT', value: storageAccountName }
            { name: 'AZURE_STORAGE_CONTAINER', value: corpusContainerName }
            { name: 'AZURE_STORAGE_RESOURCE_ID', value: storageResourceId }
            // Usados pela escrita de conhecimento e pela ingestão a partir do app.
            { name: 'AZURE_AI_OPENAI_ENDPOINT', value: azureAiOpenAiEndpoint }
            { name: 'FOUNDRY_EMBEDDING_MODEL', value: embeddingModelName }
            { name: 'AGENTS_DIR', value: '/mnt/agents' }
          ], empty(entraApiClientSecret) ? [] : [
            // Pareado com o `secrets` acima: um `secretRef` apontando para um segredo que não
            // foi declarado é o MESMO erro de deployment. Os dois aparecem ou somem juntos.
            { name: 'ENTRA_API_CLIENT_SECRET', secretRef: 'entra-api-secret' }
          ])
          volumeMounts: [
            { volumeName: 'data', mountPath: '/app/data' } // tickets.jsonl persists here
            { volumeName: 'prompts', mountPath: '/mnt/agents' } // agent definitions (read-only share)
          ]
        }
      ]
      volumes: [
        { name: 'data', storageType: 'AzureFile', storageName: envDataStorage.name }
        { name: 'prompts', storageType: 'AzureFile', storageName: envPromptsStorage.name }
      ]
      // Single replica: the persisted jsonl is append-based, so >1 writer could
      // interleave/corrupt it. Scale-to-zero still applies (idle = $0).
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}

resource webApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: webAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'web' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 3000
        transport: 'auto'
      }
      registries: [
        { server: '${registryName}.azurecr.io', identity: appIdentityId }
      ]
    }
    template: {
      containers: [
        {
          name: 'web'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1.0Gi' }
          env: [
            // Server-side (Next route handlers) — runtime env is fine here. The
            // browser-side NEXT_PUBLIC_* are baked at image build (see azure.yaml).
            { name: 'BACKEND_URL', value: 'https://${backendFqdn}' }
            { name: 'AGUI_URL', value: 'https://${backendFqdn}/helpdesk' }
            { name: 'HOSTED_AGUI_URL', value: 'https://${backendFqdn}/helpdesk-hosted' }
            // Second domain (TechDocs expert). Without this the /techdocs route proxies
            // to the localhost default and fails (405/fetch) in the container.
            { name: 'TECHDOCS_AGUI_URL', value: 'https://${backendFqdn}/techdocs' }
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 3 }  // scale-to-zero: idle = $0 (cold start on first request)
    }
  }
}

// O servidor MCP (ADR-027). SEM SEGREDO, e isso é a ADR-005 em forma de recurso: ele é um
// Resource Server — valida o token do Entra com `AzureJWTVerifier`, que não pede
// `client_secret` nenhum. Por isso não há bloco `secrets` aqui e nada a parear com ele.
//
// O que ele precisa é ler: o endpoint do Foundry e do Search (a tool `search_docs` chama o
// MESMO `knowledge.retrieve` do backend, com o trim de ACL sob a identidade de quem perguntou),
// o storage (trilha de auditoria da ADR-023 + a URL do documento) e o Entra (para saber quem é
// o chamador). NÃO precisa do share de prompts: a tool não usa as instruções dos agentes, e sem
// `AGENTS_DIR` o pacote usa a cópia embutida na imagem (ADR-014).
resource mcpApp 'Microsoft.App/containerApps@2024-03-01' = {
  name: mcpAppName
  location: location
  tags: union(tags, { 'azd-service-name': 'mcp' })
  identity: {
    type: 'UserAssigned'
    userAssignedIdentities: { '${appIdentityId}': {} }
  }
  properties: {
    managedEnvironmentId: env.id
    configuration: {
      activeRevisionsMode: 'Single'
      ingress: {
        external: true
        targetPort: 8001 // o mesmo do Dockerfile de apps/mcp
        transport: 'auto'
      }
      registries: [
        { server: '${registryName}.azurecr.io', identity: appIdentityId }
      ]
    }
    template: {
      containers: [
        {
          name: 'mcp'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1.0Gi' }
          env: [
            { name: 'FOUNDRY_PROJECT_ENDPOINT', value: foundryProjectEndpoint }
            { name: 'AZURE_SEARCH_ENDPOINT', value: azureSearchEndpoint }
            { name: 'AZURE_SEARCH_KNOWLEDGE_BASE', value: azureSearchKnowledgeBase }
            { name: 'SELFWIKI_SEARCH_KNOWLEDGE_BASE', value: 'selfwiki-kb' }
            { name: 'APP_USERS_GROUP_ID', value: appUsersGroupId }
            { name: 'AZURE_CLIENT_ID', value: appIdentityClientId }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_API_CLIENT_ID', value: entraApiClientId }
            // `resource` da metadata OAuth (RFC 9728) — o ingress DESTE app, não o do backend.
            // Sem isto o servidor anuncia o default `http://localhost:8001` e nenhum cliente MCP
            // externo descobre onde se autenticar. Era a variável que apontava para o backend
            // enquanto o `/mcp` morava lá; apontá-la para o vizinho errado é a mesma família de
            // falha do commit 007f399, só que mais silenciosa — o 401 traz uma placa que leva a
            // um host que não hospeda este recurso.
            { name: 'MCP_PUBLIC_BASE_URL', value: 'https://${mcpFqdn}' }
            { name: 'FRONTEND_ORIGIN', value: 'https://${webFqdn}' }
            { name: 'AZURE_STORAGE_ACCOUNT', value: storageAccountName }
            { name: 'AZURE_STORAGE_CONTAINER', value: corpusContainerName }
            { name: 'AZURE_STORAGE_RESOURCE_ID', value: storageResourceId }
          ]
        }
      ]
      // UMA RÉPLICA, e não por causa de arquivo: o transporte HTTP do MCP mantém sessão no
      // processo, então duas réplicas sem afinidade fariam a segunda requisição de uma sessão
      // cair num processo que não a conhece. Scale-to-zero continua valendo (ocioso = $0).
      scale: { minReplicas: 0, maxReplicas: 1 }
    }
  }
}

output BACKEND_URL string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output WEB_URL string = 'https://${webApp.properties.configuration.ingress.fqdn}'
output MCP_URL string = 'https://${mcpApp.properties.configuration.ingress.fqdn}'
