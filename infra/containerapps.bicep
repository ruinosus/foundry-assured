// Phase 7 (publish): backend + web on Azure Container Apps. azd builds each image,
// pushes to the ACR, and deploys it to the container app tagged with its
// azd-service-name. Both run as the shared user-assigned identity (created in
// resources.bicep) for ACR pull; the backend also calls Foundry + the search KB
// as that identity. The two apps reference each other by FQDN derived from the
// environment's defaultDomain, so there's no circular dependency between them.

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

@description('ACL classification group object-IDs for the grounded domains (cockpit). Populate acl_group_map so retrieval sends the per-user OBO ACL header; empty leaves ACL trim off (fail-closed on an ACL index).')
param aclPublicGroup string = ''
param aclInternalGroup string = ''
param aclConfidentialGroup string = ''

@description('Storage account backing the Azure Files share for persisted app data.')
param storageAccountName string

@description('Azure Files share mounted into the backend at /app/data (tickets.jsonl).')
param fileShareName string

@description('Blob endpoint of the storage account backing the artifacts feature (AI-generated HTML content).')
param artifactBlobAccountUrl string

@description('Table endpoint of the storage account backing the artifacts feature (artifact metadata).')
param artifactStoreAccountUrl string

@description('Azure Files share holding the runtime DNA prompt scope, mounted read-only into the backend at /mnt/dna (ADR-014). Empty share = backend falls back to the scope baked into the image.')
param promptsShareName string

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var backendAppName = 'ca-backend-${resourceToken}'
var webAppName = 'ca-web-${resourceToken}'

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

// Runtime DNA prompt scope (ADR-014, production leg). Read-only: the runtime
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
      secrets: [
        { name: 'entra-api-secret', value: entraApiClientSecret }
      ]
    }
    template: {
      containers: [
        {
          name: 'backend'
          image: placeholderImage
          resources: { cpu: json('0.5'), memory: '1.0Gi' }
          env: [
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
            { name: 'ENTRA_API_CLIENT_SECRET', secretRef: 'entra-api-secret' }
            // selfwiki audience: the app-users group is the self-wiki's private read audience;
            // retrieval sends the OBO ACL header only when this is set (else /selfwiki fails closed).
            { name: 'APP_USERS_GROUP_ID', value: appUsersGroupId }
            // cockpit ACL classification groups: populate acl_group_map so retrieval sends the
            // per-user OBO header on the cockpit ACL index (else it fails closed → "não sei").
            { name: 'ACL_PUBLIC_GROUP', value: aclPublicGroup }
            { name: 'ACL_INTERNAL_GROUP', value: aclInternalGroup }
            { name: 'ACL_CONFIDENTIAL_GROUP', value: aclConfidentialGroup }
            // Artifacts feature: metadata in Table, immutable HTML content in Blob.
            { name: 'ARTIFACT_STORE_BACKEND', value: 'table' }
            { name: 'ARTIFACT_CONTAINER', value: 'artifacts' }
            { name: 'ARTIFACT_TABLE', value: 'artifacts' }
            { name: 'ARTIFACT_BLOB_ACCOUNT_URL', value: artifactBlobAccountUrl }
            { name: 'ARTIFACT_STORE_ACCOUNT_URL', value: artifactStoreAccountUrl }
            // Runtime DNA prompt scope override (ADR-014, production leg): the
            // backend composes prompts from $DNA_BASE_DIR/helpdesk when that
            // scope exists on the mounted share, else falls back (loudly) to
            // the copy baked into the image. Prompt update = push-prompts.sh.
            { name: 'DNA_BASE_DIR', value: '/mnt/dna' }
          ]
          volumeMounts: [
            { volumeName: 'data', mountPath: '/app/data' } // tickets.jsonl persists here
            { volumeName: 'prompts', mountPath: '/mnt/dna' } // DNA prompt scope (read-only share)
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
            // Second domain (Cockpit expert). Without this the /cockpit route proxies
            // to the localhost default and fails (405/fetch) in the container.
            { name: 'COCKPIT_AGUI_URL', value: 'https://${backendFqdn}/cockpit' }
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 3 }  // scale-to-zero: idle = $0 (cold start on first request)
    }
  }
}

output BACKEND_URL string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output WEB_URL string = 'https://${webApp.properties.configuration.ingress.fqdn}'
