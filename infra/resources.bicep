// Foundry Helpdesk — resource-group-scoped resources.
//
// Phase 0: Foundry account + project + gpt-5-mini + caller data-plane role.
// Phase 1: Azure AI Search (Foundry IQ knowledge base), Storage for the corpus,
//          an embedding deployment, and the role assignments that let the search
//          managed identity reach the model + blobs, and the caller build/query
//          the knowledge base. All keyless (managed identity / Entra ID).
//
// apiVersions/types verified against microsoft-foundry/foundry-samples 00-basic,
// the Foundry Bicep quickstart, and the Azure AI Search agentic-retrieval docs.

@description('Primary location for all resources.')
param location string

@description('Tags applied to every resource.')
param tags object = {}

@description('Short unique token to make globally-unique names unique.')
param resourceToken string

@description('Principal granted data-plane roles (the deploying user). Empty skips assignments.')
param principalId string = ''

@description('Type of principalId: User for a person (default), ServicePrincipal for CI/CD. ARM rejects a mismatch.')
param principalType string = 'User'
var effectivePrincipalType = empty(principalType) ? 'User' : principalType

@description('Chat model deployment name (must match the app FOUNDRY_MODEL).')
param modelDeploymentName string = 'gpt-5-mini'

@description('Chat model version for gpt-5-mini (gpt-4.1-mini was retired/deprecating; the gpt-4.x and gpt-4o chat families are no longer GA in eastus2 — only the gpt-5.x family is).')
param modelVersion string = '2025-08-07'

@description('Chat deployment capacity (thousands of TPM). GlobalStandard is pay-per-token, so capacity is just the rate limit — keep it high so agentic retrieval + KB indexing + evals do not throttle. Lower only if you hit a subscription quota cap.')
param modelCapacity int = 100

@description('Embedding model used to vectorize the knowledge base corpus.')
param embeddingModelName string = 'text-embedding-3-small'

@description('Embedding model version.')
param embeddingModelVersion string = '1'

@description('Embedding deployment capacity (thousands of TPM). This caps the KB indexer embedding throughput — at 20 a large re-ingest crawls (~1s/chunk). GlobalStandard is pay-per-token, so raise it freely. Lower only if a subscription quota cap blocks the deploy.')
param embeddingCapacity int = 100

@description('Azure AI Search SKU. Basic is the floor for agentic retrieval (managed identity).')
param searchSkuName string = 'basic'

@description('Region for Azure AI Search. Empty falls back to the main location; override if a region is out of Search capacity.')
param searchLocation string = ''

var accountName = 'aif-assured-${resourceToken}'
var projectName = 'foundry-assured'
var searchName = 'srch-assured-${resourceToken}'
var registryName = 'acrassured${resourceToken}'
var storageName = 'stassured${resourceToken}'
var corpusContainerName = 'corpus'
var dataShareName = 'assured-data'
// ADLS Gen2 (hierarchical namespace) account for the ACL-enabled corpus (per-user document ACL on
// the agentic path needs POSIX ACLs, which require isHnsEnabled — the flat store above can't).
var adlsName = 'stadls${resourceToken}'
var aclCorpusContainerName = 'cockpit-corpus-acl'

// Built-in role definition GUIDs (stable Azure identifiers).
var roleAzureAiUser = '53ca6127-db72-4b80-b1b0-d745d6d5456d' // Azure AI User / Foundry User (Foundry data plane)
var roleCognitiveServicesUser = 'a97b65f3-24c7-4388-baec-2e87135dc908' // Cognitive Services User (call model deployments)
var roleSearchServiceContributor = '7ca78c08-252a-4471-8644-bb5ff32d4ba0' // create knowledge bases/sources
var roleSearchIndexDataReader = '1407120a-92aa-4202-b7e9-c0e197c71c8f' // query (retrieve) indexes
var roleSearchIndexDataContributor = '8ebe5a00-799e-43f5-93ac-243d3dce84a7' // write index docs: ACL stamping (acl_setup) + purge_orphans (superset of Data Reader)
var roleStorageBlobDataReader = '2a2b9908-6ea1-4ae2-8e65-a410df84e7d1' // search MI reads corpus blobs
var roleStorageBlobDataContributor = 'ba92f5b4-2d11-453d-a403-e96b0029c9fe' // caller uploads corpus blobs
var roleStorageBlobDataOwner = 'b7e6dc6d-f1e8-4753-8033-0f276bb0955b' // caller sets POSIX ACLs on ADLS Gen2 (Contributor can't)
var roleAcrPull = '7f951dda-4ed3-4680-a7ca-43fe172d538d' // project MI pulls the hosted-agent image

var searchRegion = empty(searchLocation) ? location : searchLocation

// ---------------------------------------------------------------------------
// Foundry account + project + model deployments (Phase 0, extended w/ embedding)
// ---------------------------------------------------------------------------

resource account 'Microsoft.CognitiveServices/accounts@2025-06-01' = {
  name: accountName
  location: location
  tags: tags
  kind: 'AIServices'
  sku: { name: 'S0' }
  identity: { type: 'SystemAssigned' }
  properties: {
    allowProjectManagement: true
    customSubDomainName: accountName
    disableLocalAuth: false
    publicNetworkAccess: 'Enabled'
  }
}

resource project 'Microsoft.CognitiveServices/accounts/projects@2025-06-01' = {
  name: projectName
  parent: account
  location: location
  tags: tags
  identity: { type: 'SystemAssigned' }
  properties: {}
}

resource modelDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: modelDeploymentName
  sku: { name: 'GlobalStandard', capacity: modelCapacity }
  properties: {
    model: {
      name: modelDeploymentName
      format: 'OpenAI'
      version: modelVersion
    }
  }
}

// Deployments on the same account must be created sequentially.
resource embeddingDeployment 'Microsoft.CognitiveServices/accounts/deployments@2025-06-01' = {
  parent: account
  name: embeddingModelName
  sku: { name: 'GlobalStandard', capacity: embeddingCapacity }
  properties: {
    model: {
      name: embeddingModelName
      format: 'OpenAI'
      version: embeddingModelVersion
    }
  }
  dependsOn: [ modelDeployment ]
}

// ---------------------------------------------------------------------------
// Observability: Log Analytics + Application Insights, connected to the Foundry
// account so agent-framework's OpenTelemetry GenAI spans (gen_ai.usage.*) land in
// the Foundry "Tracing" / App Insights "Agents" view. The category 'AppInsights'
// connection is what `project.telemetry.get_application_insights_connection_string()`
// reads. Connection schema verified against the Microsoft.CognitiveServices/
// accounts/connections template reference (category/authType/credentials).
// ---------------------------------------------------------------------------

resource logAnalytics 'Microsoft.OperationalInsights/workspaces@2023-09-01' = {
  name: 'log-assured-${resourceToken}'
  location: location
  tags: tags
  properties: {
    sku: { name: 'PerGB2018' }
    retentionInDays: 30
  }
}

resource appInsights 'Microsoft.Insights/components@2020-02-02' = {
  name: 'appi-assured-${resourceToken}'
  location: location
  tags: tags
  kind: 'web'
  properties: {
    Application_Type: 'web'
    WorkspaceResourceId: logAnalytics.id
  }
}

// Account-level connection (shared to all projects) — the telemetry target Foundry reads.
resource appInsightsConnection 'Microsoft.CognitiveServices/accounts/connections@2025-06-01' = {
  name: 'appinsights'
  parent: account
  properties: {
    category: 'AppInsights'
    target: appInsights.id
    authType: 'ApiKey'
    credentials: {
      key: appInsights.properties.ConnectionString
    }
    isSharedToAll: true
    metadata: {
      ApiType: 'Azure'
      ResourceId: appInsights.id
    }
  }
}

// ---------------------------------------------------------------------------
// Storage for the knowledge base corpus (blob knowledge source)
// ---------------------------------------------------------------------------

resource storage 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: storageName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: true
  }
}

resource blobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource corpusContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: blobService
  name: corpusContainerName
  properties: { publicAccess: 'None' }
}

// File share mounted by the backend container app (Azure Files) so app data written
// to /app/data (tickets.jsonl) survives scale-to-zero / restarts. Small + cheap.
resource fileService 'Microsoft.Storage/storageAccounts/fileServices@2023-05-01' = {
  parent: storage
  name: 'default'
}

resource dataShare 'Microsoft.Storage/storageAccounts/fileServices/shares@2023-05-01' = {
  parent: fileService
  name: dataShareName
  properties: { shareQuota: 1 } // GiB — jsonl records are tiny
}

// ---------------------------------------------------------------------------
// ADLS Gen2 storage for the ACL-enabled corpus (native per-user document ACL)
// ---------------------------------------------------------------------------
// The agentic knowledge_base_retrieve enforces per-user document ACL only when the knowledge source
// ingests POSIX ACLs (ingestionPermissionOptions=[groupIds/userIds]), which are ONLY supported on an
// ADLS Gen2 (isHnsEnabled) account — a flat blob source rejects groupIds. So the ACL corpus lives
// here, uploaded with per-file POSIX ACLs derived from the manifest read-groups (app/knowledge/*).
resource adls 'Microsoft.Storage/storageAccounts@2023-05-01' = {
  name: adlsName
  location: location
  tags: tags
  sku: { name: 'Standard_LRS' }
  kind: 'StorageV2'
  properties: {
    isHnsEnabled: true
    allowBlobPublicAccess: false
    minimumTlsVersion: 'TLS1_2'
    allowSharedKeyAccess: true
  }
}

resource adlsBlobService 'Microsoft.Storage/storageAccounts/blobServices@2023-05-01' = {
  parent: adls
  name: 'default'
}

resource aclCorpusContainer 'Microsoft.Storage/storageAccounts/blobServices/containers@2023-05-01' = {
  parent: adlsBlobService
  name: aclCorpusContainerName
  properties: { publicAccess: 'None' }
}

// ---------------------------------------------------------------------------
// Azure AI Search (the Foundry IQ knowledge base lives here)
// ---------------------------------------------------------------------------

resource search 'Microsoft.Search/searchServices@2024-06-01-preview' = {
  name: searchName
  location: searchRegion
  tags: tags
  sku: { name: searchSkuName }
  identity: { type: 'SystemAssigned' }
  properties: {
    replicaCount: 1
    partitionCount: 1
    hostingMode: 'default'
    semanticSearch: 'free' // enables semantic ranker (agentic retrieval) within the free 1k/month quota
    authOptions: {
      aadOrApiKey: { aadAuthFailureMode: 'http401WithBearerChallenge' }
    }
  }
}

// ---------------------------------------------------------------------------
// Container registry for the Phase 6 hosted agent image (azd builds + pushes
// here; Foundry Agent Service pulls from here at deploy time). Public endpoint —
// private ACR isn't supported for hosted agents.
// ---------------------------------------------------------------------------

resource registry 'Microsoft.ContainerRegistry/registries@2023-11-01-preview' = {
  name: registryName
  location: location
  tags: tags
  sku: { name: 'Basic' }
  properties: {
    adminUserEnabled: false
    anonymousPullEnabled: false
  }
}

// User-assigned identity shared by the Container Apps (backend + web) when
// publishing to Azure. Pulls images from ACR and (for the backend) calls Foundry
// + the search KB as itself. Created here so all its RBAC lives with the targets.
resource appIdentity 'Microsoft.ManagedIdentity/userAssignedIdentities@2023-01-31' = {
  name: 'id-assured-app-${resourceToken}'
  location: location
  tags: tags
}

resource appToRegistry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, appIdentity.id, roleAcrPull)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAcrPull)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource appToFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, appIdentity.id, roleAzureAiUser)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAzureAiUser)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

resource appToSearch 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(search.id, appIdentity.id, roleSearchIndexDataReader)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleSearchIndexDataReader)
    principalId: appIdentity.properties.principalId
    principalType: 'ServicePrincipal'
  }
}

// ---------------------------------------------------------------------------
// Role assignments (keyless wiring)
// ---------------------------------------------------------------------------

// Search MI -> call embedding + query-planning models on the Foundry account.
resource searchToFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, search.id, roleCognitiveServicesUser)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleCognitiveServicesUser)
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Foundry project MI -> Azure AI User on the account. Per the memory docs, this
// lets the memory runtime invoke the chat + embedding deployments server-side.
// (Without it: 401 "Authentication to the Azure OpenAI resource failed".)
resource projectToFoundry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(account.id, project.id, roleAzureAiUser)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAzureAiUser)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Foundry project MI -> pull the hosted-agent image from ACR at runtime
// (Container Registry Repository Reader / AcrPull). Without it: image_pull_failed.
resource projectToRegistry 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(registry.id, project.id, roleAcrPull)
  scope: registry
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAcrPull)
    principalId: project.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Search MI -> read corpus blobs during ingestion.
resource searchToStorage 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(storage.id, search.id, roleStorageBlobDataReader)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageBlobDataReader)
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Caller (deploying user) -> create knowledge base + knowledge source.
resource userSearchContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(search.id, principalId, roleSearchServiceContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleSearchServiceContributor)
    principalId: principalId
    principalType: effectivePrincipalType
  }
}

// Caller -> query (retrieve) the KB AND write index docs. The data-plane ingest writes documents
// directly as the caller: document-level ACL stamping (app/knowledge/acl_setup.py) and orphan
// reconciliation (ingest_cockpit.purge_orphans) both need Search Index Data Contributor — Reader
// can only query, so a from-scratch `azd up` would 403 on ACL stamping without this. Contributor
// is a superset of Data Reader, so it also covers retrieval from the local backend.
resource userSearchIndexContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(search.id, principalId, roleSearchIndexDataContributor)
  scope: search
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleSearchIndexDataContributor)
    principalId: principalId
    principalType: effectivePrincipalType
  }
}

// Caller -> upload corpus markdown to blob during ingestion.
resource userStorageContributor 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(storage.id, principalId, roleStorageBlobDataContributor)
  scope: storage
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageBlobDataContributor)
    principalId: principalId
    principalType: effectivePrincipalType
  }
}

// Search MI -> read the ADLS Gen2 corpus + its POSIX ACLs during ingestion. Data OWNER (not just
// Reader): ingesting POSIX ACLs as permission metadata requires reading each file's ACL
// (getAccessControl), which Storage Blob Data Reader does NOT permit — only Owner can read/manage
// ACLs. Owner is a superset of Reader, so it also covers content reads for indexing.
resource searchToAdls 'Microsoft.Authorization/roleAssignments@2022-04-01' = {
  name: guid(adls.id, search.id, roleStorageBlobDataOwner)
  scope: adls
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageBlobDataOwner)
    principalId: search.identity.principalId
    principalType: 'ServicePrincipal'
  }
}

// Caller -> upload the ACL corpus AND set per-file POSIX ACLs. Setting ACLs on ADLS Gen2 requires
// Storage Blob Data Owner (Data Contributor can write blobs but NOT set ACLs), so the ingest
// (app/knowledge/ingest_cockpit.py) can stamp each file's read-groups.
resource userAdlsOwner 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(adls.id, principalId, roleStorageBlobDataOwner)
  scope: adls
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleStorageBlobDataOwner)
    principalId: principalId
    principalType: effectivePrincipalType
  }
}

// Caller -> Foundry data plane (Phase 0; kept here so the whole stack is one template).
resource userAiUser 'Microsoft.Authorization/roleAssignments@2022-04-01' = if (!empty(principalId)) {
  name: guid(account.id, principalId, roleAzureAiUser)
  scope: account
  properties: {
    roleDefinitionId: subscriptionResourceId('Microsoft.Authorization/roleDefinitions', roleAzureAiUser)
    principalId: principalId
    principalType: effectivePrincipalType
  }
}

// ---------------------------------------------------------------------------
// Outputs (surfaced by azd into .azure/<env>/.env)
// ---------------------------------------------------------------------------

output FOUNDRY_PROJECT_ENDPOINT string = 'https://${accountName}.services.ai.azure.com/api/projects/${projectName}'
// ARM resource id of the Foundry project — azd reads this (AZURE_AI_PROJECT_ID) to resolve the
// target project when deploying hosted agents (azure.ai.agent). Surfacing it as an output keeps it
// in lockstep with the account/project names — so a rename never leaves a stale manually-set value.
output AZURE_AI_PROJECT_ID string = project.id
// ARM ids of the account + search — read by the postdeploy hook (scripts/hook-postdeploy.sh) to
// grant each hosted agent's deploy-time instance identity its runtime roles (Azure AI User on the
// account, Search Index Data Reader on search), which Bicep can't pre-assign (identity is minted at deploy).
output AZURE_AI_ACCOUNT_ID string = account.id
output AZURE_SEARCH_ID string = search.id
output AZURE_AI_ACCOUNT_ENDPOINT string = account.properties.endpoint
output AZURE_AI_OPENAI_ENDPOINT string = 'https://${accountName}.openai.azure.com'
output FOUNDRY_MODEL string = modelDeploymentName
output FOUNDRY_EMBEDDING_MODEL string = embeddingModelName

// Observability — set in the local/app env to export gen_ai OTEL spans to App Insights.
output APPLICATIONINSIGHTS_CONNECTION_STRING string = appInsights.properties.ConnectionString

output AZURE_SEARCH_ENDPOINT string = 'https://${searchName}.search.windows.net'
output AZURE_SEARCH_KNOWLEDGE_BASE string = 'helpdesk-kb'

output AZURE_STORAGE_ACCOUNT string = storage.name
output AZURE_STORAGE_RESOURCE_ID string = storage.id
output AZURE_STORAGE_CONTAINER string = corpusContainerName
output AZURE_FILE_SHARE string = dataShareName

// ADLS Gen2 account for the ACL-enabled corpus (read by ingest_cockpit for the native-ACL path).
output AZURE_ADLS_ACCOUNT string = adls.name
output AZURE_ADLS_RESOURCE_ID string = adls.id
output AZURE_ADLS_CONTAINER string = aclCorpusContainerName

// Consumed by azd (and the agent extension) to build/push the hosted-agent image.
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = registry.properties.loginServer
output AZURE_CONTAINER_REGISTRY_NAME string = registry.name

// Shared app identity for the Container Apps (backend + web).
output APP_IDENTITY_ID string = appIdentity.id
output APP_IDENTITY_CLIENT_ID string = appIdentity.properties.clientId
