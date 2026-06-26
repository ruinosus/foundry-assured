// Foundry Helpdesk — azd entry point (subscription-scoped).
//
// Provisions a resource group, then the Foundry account + project + gpt-4.1-mini
// deployment + data-plane role assignment (in resources.bicep).
//
// Schema verified against the official Foundry sample
// (microsoft-foundry/foundry-samples 00-basic) and the learn.microsoft.com
// Bicep quickstart — resource types/apiVersions are not invented (CLAUDE.md #1).

targetScope = 'subscription'

@minLength(1)
@maxLength(64)
@description('Name of the azd environment — derives resource names and tags.')
param environmentName string

@description('Primary location for all resources (azd prompts for this).')
param location string

@description('Object ID granted data-plane access. azd sets this from AZURE_PRINCIPAL_ID.')
param principalId string = ''

@description('Type of principalId: User locally, ServicePrincipal in CI/CD (azd maps AZURE_PRINCIPAL_TYPE).')
param principalType string = 'User'

@description('Model deployment name, surfaced to the app as FOUNDRY_MODEL.')
param modelDeploymentName string = 'gpt-4.1-mini'

@description('Optional region override for Azure AI Search (set AZURE_SEARCH_LOCATION if eastus2 is out of Search capacity). Falls back to location.')
param searchLocation string = ''

@description('Entra tenant for backend OBO (optional; azd maps ENTRA_TENANT_ID).')
param entraTenantId string = ''

@description('Backend API app client id for OBO (optional; azd maps ENTRA_API_CLIENT_ID).')
param entraApiClientId string = ''

@secure()
@description('Backend API app client secret for OBO (optional; azd maps ENTRA_API_CLIENT_SECRET).')
param entraApiClientSecret string = ''

var resourceToken = toLower(uniqueString(subscription().id, environmentName, location))
var effectiveSearchLocation = empty(searchLocation) ? location : searchLocation
var tags = { 'azd-env-name': environmentName }

resource rg 'Microsoft.Resources/resourceGroups@2024-03-01' = {
  name: 'rg-${environmentName}'
  location: location
  tags: tags
}

module resources 'resources.bicep' = {
  name: 'resources'
  scope: rg
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: principalId
    principalType: principalType // 'User' locally, 'ServicePrincipal' in CI/CD
    modelDeploymentName: modelDeploymentName
    searchLocation: effectiveSearchLocation // region override for AI Search capacity
  }
}

// Phase 7 (publish) — backend + web on Container Apps. azd builds/pushes the
// images and deploys them to the apps tagged backend/web in this module.
module apps 'containerapps.bicep' = {
  name: 'containerapps'
  scope: rg
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    registryName: resources.outputs.AZURE_CONTAINER_REGISTRY_NAME
    appIdentityId: resources.outputs.APP_IDENTITY_ID
    appIdentityClientId: resources.outputs.APP_IDENTITY_CLIENT_ID
    foundryProjectEndpoint: resources.outputs.FOUNDRY_PROJECT_ENDPOINT
    foundryModel: resources.outputs.FOUNDRY_MODEL
    azureSearchEndpoint: resources.outputs.AZURE_SEARCH_ENDPOINT
    azureSearchKnowledgeBase: resources.outputs.AZURE_SEARCH_KNOWLEDGE_BASE
    storageAccountName: resources.outputs.AZURE_STORAGE_ACCOUNT
    fileShareName: resources.outputs.AZURE_FILE_SHARE
    entraTenantId: entraTenantId
    entraApiClientId: entraApiClientId
    entraApiClientSecret: entraApiClientSecret
  }
}

output BACKEND_URL string = apps.outputs.BACKEND_URL
output WEB_URL string = apps.outputs.WEB_URL

// Surfaced into .azure/<env>/.env by azd — feed these to the backend / ingestion.
output FOUNDRY_PROJECT_ENDPOINT string = resources.outputs.FOUNDRY_PROJECT_ENDPOINT
output FOUNDRY_MODEL string = resources.outputs.FOUNDRY_MODEL
output FOUNDRY_EMBEDDING_MODEL string = resources.outputs.FOUNDRY_EMBEDDING_MODEL
output AZURE_AI_ACCOUNT_ENDPOINT string = resources.outputs.AZURE_AI_ACCOUNT_ENDPOINT
output AZURE_AI_OPENAI_ENDPOINT string = resources.outputs.AZURE_AI_OPENAI_ENDPOINT

output AZURE_SEARCH_ENDPOINT string = resources.outputs.AZURE_SEARCH_ENDPOINT
output AZURE_SEARCH_KNOWLEDGE_BASE string = resources.outputs.AZURE_SEARCH_KNOWLEDGE_BASE

output AZURE_STORAGE_ACCOUNT string = resources.outputs.AZURE_STORAGE_ACCOUNT
output AZURE_STORAGE_RESOURCE_ID string = resources.outputs.AZURE_STORAGE_RESOURCE_ID
output AZURE_STORAGE_CONTAINER string = resources.outputs.AZURE_STORAGE_CONTAINER

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.AZURE_CONTAINER_REGISTRY_ENDPOINT
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.AZURE_CONTAINER_REGISTRY_NAME
