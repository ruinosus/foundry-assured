// Foundry Helpdesk — azd entry point (subscription-scoped).
//
// Provisions a resource group, then the Foundry account + project + gpt-5-mini
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

@description('Entra group of app users, granted Foundry User so they can run inference as themselves (OBO). azd maps APP_USERS_GROUP_ID. Empty skips.')
param appUsersGroupId string = ''

@description('Type of principalId: User locally, ServicePrincipal in CI/CD (azd maps AZURE_PRINCIPAL_TYPE).')
param principalType string = 'User'

@description('Object ID of the CI/CD service principal (the OIDC deploy identity), granted the SAME data-plane roles as principalId. Separate because principalId holds whoever ran the last provision — in practice a person — so CI would otherwise never receive them. azd maps AZURE_CI_PRINCIPAL_ID. Empty skips.')
param ciPrincipalId string = ''

@description('Model deployment name, surfaced to the app as FOUNDRY_MODEL.')
param modelDeploymentName string = 'gpt-5-mini'

@description('Deploy Azure AI Search (default true). FALSE gives an environment for the model-driven domains only — helpdesk workflow, platform MCP and the LangGraph oncall domain — without the ~US$74/month the Basic tier costs simply for existing. The grounded domains and the per-document ACL need it.')
param deploySearch bool = true

@description('Optional region override for Azure AI Search (set AZURE_SEARCH_LOCATION if eastus2 is out of Search capacity). Falls back to location.')
param searchLocation string = ''

@description('Entra tenant for backend OBO (optional; azd maps ENTRA_TENANT_ID).')
param entraTenantId string = ''

@description('Backend API app client id for OBO (optional; azd maps ENTRA_API_CLIENT_ID).')
param entraApiClientId string = ''

@secure()
@description('Backend API app client secret for OBO (optional; azd maps ENTRA_API_CLIENT_SECRET).')
param entraApiClientSecret string = ''

@secure()
@description('Chave (>= 32 bytes) que assina o `requestState` da decisão humana do servidor MCP (azd mapeia MCP_REQUEST_STATE_KEY). Vem do cofre para o ambiente — nunca do repositório (ADR-005). Vazia: a escrita por MCP fica indisponível, o resto do servidor não muda. Gere com: python -c "import secrets; print(secrets.token_hex(32))"')
param mcpRequestStateKey string = ''

@secure()
@description('Chave que cifra o snapshot de contexto das background tasks do MCP em repouso no Redis (azd mapeia MCP_TASKS_ENCRYPTION_KEY). O snapshot carrega o access token de quem submeteu — sem a chave, o pacote grava JSON em claro. Vazia: as tasks não sobem e a busca continua síncrona. Gere com: python -c "import secrets; print(secrets.token_hex(32))"')
param mcpTasksEncryptionKey string = ''

@description('Provisiona o Azure Cache for Redis (Basic C0, ~US$16/mês SEMPRE LIGADO) que sustenta as background tasks e a sessão por usuário do servidor MCP. FALSE mantém o ocioso em zero: a busca só roda síncrona e a sessão vira memória de processo, que o scale-to-zero apaga.')
param deployRedis bool = true

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
    ciPrincipalId: ciPrincipalId
    appUsersGroupId: appUsersGroupId
    modelDeploymentName: modelDeploymentName
    deploySearch: deploySearch
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
    corpusContainerName: resources.outputs.AZURE_STORAGE_CONTAINER
    storageResourceId: resources.outputs.AZURE_STORAGE_RESOURCE_ID
    azureAiOpenAiEndpoint: resources.outputs.AZURE_AI_OPENAI_ENDPOINT
    embeddingModelName: resources.outputs.FOUNDRY_EMBEDDING_MODEL
    fileShareName: resources.outputs.AZURE_FILE_SHARE
    promptsShareName: resources.outputs.AZURE_PROMPTS_FILE_SHARE
    entraTenantId: entraTenantId
    entraApiClientId: entraApiClientId
    entraApiClientSecret: entraApiClientSecret
    mcpRequestStateKey: mcpRequestStateKey
    mcpTasksEncryptionKey: mcpTasksEncryptionKey
    deployRedis: deployRedis
    appUsersGroupId: appUsersGroupId
  }
}

output BACKEND_URL string = apps.outputs.BACKEND_URL
output WEB_URL string = apps.outputs.WEB_URL
output MCP_URL string = apps.outputs.MCP_URL

// Surfaced into .azure/<env>/.env by azd — feed these to the backend / ingestion.
output FOUNDRY_PROJECT_ENDPOINT string = resources.outputs.FOUNDRY_PROJECT_ENDPOINT
// O azd EXIGE isto no ambiente para invocar qualquer hook — sem ele, `azd deploy` aborta com
// "AZURE_TENANT_ID is not set in the environment" DEPOIS de já ter publicado o serviço, e o
// `continueOnError: true` do hook não protege: o erro é do azd invocando, não do script rodando.
// Nada no repositório definia este valor; ele só existia por acaso, quando o azd o herdava do
// login. Ambiente novo, ou clone de outra pessoa, ficava sem — que é o caso que motivou o output.
output AZURE_TENANT_ID string = tenant().tenantId

output AZURE_AI_PROJECT_ID string = resources.outputs.AZURE_AI_PROJECT_ID   // azd uses this to deploy hosted agents
output AZURE_AI_ACCOUNT_ID string = resources.outputs.AZURE_AI_ACCOUNT_ID   // postdeploy hook: agent RBAC scope
output AZURE_SEARCH_ID string = resources.outputs.AZURE_SEARCH_ID           // postdeploy hook: agent RBAC scope
output FOUNDRY_MODEL string = resources.outputs.FOUNDRY_MODEL
output FOUNDRY_EMBEDDING_MODEL string = resources.outputs.FOUNDRY_EMBEDDING_MODEL
output AZURE_AI_ACCOUNT_ENDPOINT string = resources.outputs.AZURE_AI_ACCOUNT_ENDPOINT
output AZURE_AI_OPENAI_ENDPOINT string = resources.outputs.AZURE_AI_OPENAI_ENDPOINT

output AZURE_SEARCH_ENDPOINT string = resources.outputs.AZURE_SEARCH_ENDPOINT
output AZURE_SEARCH_KNOWLEDGE_BASE string = resources.outputs.AZURE_SEARCH_KNOWLEDGE_BASE

output AZURE_STORAGE_ACCOUNT string = resources.outputs.AZURE_STORAGE_ACCOUNT
output AZURE_STORAGE_RESOURCE_ID string = resources.outputs.AZURE_STORAGE_RESOURCE_ID
output AZURE_STORAGE_CONTAINER string = resources.outputs.AZURE_STORAGE_CONTAINER
output AZURE_PROMPTS_FILE_SHARE string = resources.outputs.AZURE_PROMPTS_FILE_SHARE // push-prompts.sh reads this from the azd env

output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.AZURE_CONTAINER_REGISTRY_ENDPOINT
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.AZURE_CONTAINER_REGISTRY_NAME

// Lido pelo deploy.yml logo após `azd provision` para reprovar o job se o CI ficou sem as
// roles de dado (ver comentário em resources.bicep).
output CI_DATA_PLANE_ROLES_ASSIGNED bool = resources.outputs.CI_DATA_PLANE_ROLES_ASSIGNED
