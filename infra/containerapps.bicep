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

@description('Storage account backing the Azure Files share for persisted app data.')
param storageAccountName string

@description('Azure Files share mounted into the backend at /app/data (tickets.jsonl).')
param fileShareName string

var placeholderImage = 'mcr.microsoft.com/azuredocs/containerapps-helloworld:latest'
var backendAppName = 'ca-backend-${resourceToken}'
var webAppName = 'ca-web-${resourceToken}'

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-helpdesk-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource env 'Microsoft.App/managedEnvironments@2024-03-01' = {
  name: 'cae-helpdesk-${resourceToken}'
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
            { name: 'FRONTEND_ORIGIN', value: 'https://${webFqdn}' }
            { name: 'AZURE_CLIENT_ID', value: appIdentityClientId }
            { name: 'ENTRA_TENANT_ID', value: entraTenantId }
            { name: 'ENTRA_API_CLIENT_ID', value: entraApiClientId }
            { name: 'ENTRA_API_CLIENT_SECRET', secretRef: 'entra-api-secret' }
          ]
          volumeMounts: [
            { volumeName: 'data', mountPath: '/app/data' } // tickets.jsonl persists here
          ]
        }
      ]
      volumes: [
        { name: 'data', storageType: 'AzureFile', storageName: envDataStorage.name }
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
          ]
        }
      ]
      scale: { minReplicas: 0, maxReplicas: 3 }  // scale-to-zero: idle = $0 (cold start on first request)
    }
  }
}

output BACKEND_URL string = 'https://${backendApp.properties.configuration.ingress.fqdn}'
output WEB_URL string = 'https://${webApp.properties.configuration.ingress.fqdn}'
