// Foundry Helpdesk — Azure Managed Application root template (dedicated stamp).
//
// ADR-001/ADR-002: the dedicated stamp is delivered as an Azure Managed
// Application. The publisher (us) operates the control plane; it deploys into a
// platform-provided *managed resource group* inside the CUSTOMER's subscription,
// which the customer cannot directly modify. "Everything is the customer's,"
// with us as operator.
//
// Unlike `infra/main.bicep` (subscription-scoped: it creates its own
// `Microsoft.Resources/resourceGroups`), a Managed Application's mainTemplate is
// deployed by the platform INTO the managed RG it already created — so this
// template is `targetScope = 'resourceGroup'` and declares NO resourceGroups
// resource. It is a customer-subscription RE-PARAMETERIZATION of the same
// `infra/resources.bicep` + `infra/containerapps.bicep` modules (ADR-002), not a
// duplicate of the resource definitions.
//
// Compiled to the required root `mainTemplate.json` (ARM JSON) via `bicep build`
// (see build.sh). apiVersions/types are inherited from the shared modules, which
// are verified against the Foundry sample (CLAUDE.md rule #1).

targetScope = 'resourceGroup'

@description('Primary location for all resources. Defaults to the managed RG location.')
param location string = resourceGroup().location

@description('Chat model deployment name, surfaced to the app as FOUNDRY_MODEL.')
param modelDeploymentName string = 'gpt-5-mini'

@description('Optional region override for Azure AI Search (set if the primary region is out of Search capacity). Empty falls back to location.')
param searchLocation string = ''

@description('Entra tenant for backend OBO (optional).')
param entraTenantId string = ''

@description('Backend API app client id for OBO (optional).')
param entraApiClientId string = ''

@secure()
@description('Backend API app client secret for OBO (optional).')
param entraApiClientSecret string = ''

// Managed RG name + the managed-app deployment already make the names unique per
// customer subscription; derive the resource token the same way the azd path does
// but from the managed RG identity (resourceGroup().id) so re-deploys are stable.
var resourceToken = toLower(uniqueString(subscription().id, resourceGroup().id, location))
var tags = { 'foundry-assured-stamp': 'managed-app' }

// DEPLOYMENT-MODE CAVEAT (read before the two module compositions below):
// BOTH composed modules — '../resources.bicep' and '../containerapps.bicep' —
// declare a Log Analytics workspace named `log-assured-${resourceToken}` (same
// name, identical body; pre-existing in the shared modules). As two separate
// nested module deployments this COMPILES CLEAN and CONVERGES under ARM
// **Incremental** mode (both deploy the same workspace → idempotent). It is
// fragile under **Complete** mode, where reconciliation of a duplicate-named
// resource declared by two modules is undefined/foot-gun territory.
// => Managed-application updates for THIS template must use **Incremental** mode
//    (see docs/D-PACKAGING-RUNBOOK.md). Do not switch to Complete here.

// Foundry account + project + model + search + storage + registry + app identity.
// principalId is intentionally EMPTY: in the managed-app model the publisher
// operates the stamp, so no deploying-user data-plane grant is created here
// (the conditional caller role assignments in resources.bicep are skipped when
// principalId is empty — fail-closed by default).
module resources '../resources.bicep' = {
  name: 'resources'
  params: {
    location: location
    tags: tags
    resourceToken: resourceToken
    principalId: ''
    modelDeploymentName: modelDeploymentName
    searchLocation: searchLocation
  }
}

// Backend + web on Azure Container Apps, re-parameterized from the module outputs
// (identical wiring to infra/main.bicep's `apps` module).
module apps '../containerapps.bicep' = {
  name: 'containerapps'
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
    promptsShareName: resources.outputs.AZURE_PROMPTS_FILE_SHARE
    entraTenantId: entraTenantId
    entraApiClientId: entraApiClientId
    entraApiClientSecret: entraApiClientSecret
  }
}

output BACKEND_URL string = apps.outputs.BACKEND_URL
output WEB_URL string = apps.outputs.WEB_URL

// Surfaced for the publisher's post-deploy wiring (hosted agent + Toolbox, see
// docs/D-PACKAGING-RUNBOOK.md).
output FOUNDRY_PROJECT_ENDPOINT string = resources.outputs.FOUNDRY_PROJECT_ENDPOINT
output FOUNDRY_MODEL string = resources.outputs.FOUNDRY_MODEL
output AZURE_SEARCH_ENDPOINT string = resources.outputs.AZURE_SEARCH_ENDPOINT
output AZURE_SEARCH_KNOWLEDGE_BASE string = resources.outputs.AZURE_SEARCH_KNOWLEDGE_BASE
output AZURE_CONTAINER_REGISTRY_ENDPOINT string = resources.outputs.AZURE_CONTAINER_REGISTRY_ENDPOINT
output AZURE_CONTAINER_REGISTRY_NAME string = resources.outputs.AZURE_CONTAINER_REGISTRY_NAME
