# Arquitetura da Infraestrutura — fatos extraídos dos arquivos fonte

- Em entra/bicepconfig.json:
  - experimentalFeaturesEnabled.extensibility está definido como true (entra/bicepconfig.json:3).
  - Há uma entrada em "extensions" chamada "microsoftGraphV1" com o valor "br:mcr.microsoft.com/bicep/extensions/microsoftgraph/v1.0:0.1.8-preview" (entra/bicepconfig.json:6).

- Em main.parameters.json:
  - O arquivo referencia o esquema https://schema.management.azure.com/schemas/2019-04-01/deploymentParameters.json# (main.parameters.json:2).
  - contentVersion está definido como "1.0.0.0" (main.parameters.json:3).
  - Os parâmetros presentes e seus valores literais no arquivo são:
    - environmentName: "${AZURE_ENV_NAME}" (main.parameters.json:5)
    - location: "${AZURE_LOCATION}" (main.parameters.json:6)
    - principalId: "${AZURE_PRINCIPAL_ID}" (main.parameters.json:7)
    - principalType: "${AZURE_PRINCIPAL_TYPE}" (main.parameters.json:8)
    - searchLocation: "${AZURE_SEARCH_LOCATION}" (main.parameters.json:9)
    - entraTenantId: "${ENTRA_TENANT_ID}" (main.parameters.json:10)
    - entraApiClientId: "${ENTRA_API_CLIENT_ID}" (main.parameters.json:11)
    - entraApiClientSecret: "${ENTRA_API_CLIENT_SECRET}" (main.parameters.json:12)