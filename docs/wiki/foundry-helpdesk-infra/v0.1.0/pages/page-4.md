## Fatos extraídos dos arquivos-fonte

- entra/bicepconfig.json define "experimentalFeaturesEnabled"."extensibility" como true. (entra/bicepconfig.json:1-8)
- entra/bicepconfig.json define uma extensão "microsoftGraphV1" com o valor "br:mcr.microsoft.com/bicep/extensions/microsoftgraph/v1.0:0.1.8-preview". (entra/bicepconfig.json:1-8)

- main.parameters.json define "$schema" como "https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json#". (main.parameters.json:2)
- main.parameters.json define "contentVersion" como "1.0.0.0". (main.parameters.json:3)
- main.parameters.json contém os parâmetros:
  - environmentName — valor "${AZURE_ENV_NAME}" (main.parameters.json:5)
  - location — valor "${AZURE_LOCATION}" (main.parameters.json:6)
  - principalId — valor "${AZURE_PRINCIPAL_ID}" (main.parameters.json:7)
  - principalType — valor "${AZURE_PRINCIPAL_TYPE}" (main.parameters.json:8)
  - searchLocation — valor "${AZURE_SEARCH_LOCATION}" (main.parameters.json:9)
  - entraTenantId — valor "${ENTRA_TENANT_ID}" (main.parameters.json:10)
  - entraApiClientId — valor "${ENTRA_API_CLIENT_ID}" (main.parameters.json:11)
  - entraApiClientSecret — valor "${ENTRA_API_CLIENT_SECRET}" (main.parameters.json:12)