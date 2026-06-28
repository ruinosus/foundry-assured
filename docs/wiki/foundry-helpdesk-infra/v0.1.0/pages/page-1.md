# Visão Geral

- Arquivo entra/bicepconfig.json:
  - "experimentalFeaturesEnabled"."extensibility" está definido como true (entra/bicepconfig.json).
  - "extensions"."microsoftGraphV1" está definido como "br:mcr.microsoft.com/bicep/extensions/microsoftgraph/v1.0:0.1.8-preview" (entra/bicepconfig.json).

- Arquivo main.parameters.json:
  - "$schema" está definido como "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#" (main.parameters.json).
  - "contentVersion" está definido como "1.0.0.0" (main.parameters.json).
  - Há um objeto "parameters" contendo as entradas seguintes com seus respectivos valores:
    - "environmentName": { "value": "${AZURE_ENV_NAME}" } (main.parameters.json).
    - "location": { "value": "${AZURE_LOCATION}" } (main.parameters.json).
    - "principalId": { "value": "${AZURE_PRINCIPAL_ID}" } (main.parameters.json).
    - "principalType": { "value": "${AZURE_PRINCIPAL_TYPE}" } (main.parameters.json).
    - "searchLocation": { "value": "${AZURE_SEARCH_LOCATION}" } (main.parameters.json).
    - "entraTenantId": { "value": "${ENTRA_TENANT_ID}" } (main.parameters.json).
    - "entraApiClientId": { "value": "${ENTRA_API_CLIENT_ID}" } (main.parameters.json).
    - "entraApiClientSecret": { "value": "${ENTRA_API_CLIENT_SECRET}" } (main.parameters.json).