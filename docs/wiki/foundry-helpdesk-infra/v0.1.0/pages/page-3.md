local-only

# Provisionamento e Deploy

A seguir estão apenas afirmações diretamente suportadas pelos arquivos fornecidos.

## Arquivos e pontos-chave

- entra/bicepconfig.json define uma configuração de Bicep com "experimentalFeaturesEnabled.extensibility" definido como true e uma extensão "microsoftGraphV1" apontando para "br:mcr.microsoft.com/bicep/extensions/microsoftgraph/v1.0:0.1.8-preview". (entra/bicepconfig.json:1-7)

- entra/create-acl-identities.sh é um script bash que se apresenta como "Phase 4 — PORTABLE identity bootstrap for document-level access control." e contém comentários explicando intenções de uso e motivos do script. (entra/create-acl-identities.sh:1-15)

- O mesmo script define variáveis obrigatórias de entrada DOMAIN e PW a partir dos parâmetros positionais e usa set -euo pipefail. (entra/create-acl-identities.sh:17-20)

- O script implementa a função create_group que verifica um grupo via `az ad group show` e, se não existir, cria o grupo com `az ad group create` retornando o id. (entra/create-acl-identities.sh:22-31, 24-26)

- O script implementa a função create_user que verifica um usuário via `az ad user show` e, se não existir, cria o usuário com `az ad user create` usando --password "$PW" e --force-change-password-next-sign-in true, retornando o id. (entra/create-acl-identities.sh:34-45, 36-39)

- O script cria (invoca create_group para) três grupos com os display names e mailNicknames:
  - "SEC-cockpit-kb-public" / "sec-cockpit-kb-public"
  - "SEC-cockpit-kb-internal" / "sec-cockpit-kb-internal"
  - "SEC-cockpit-kb-confidential" / "sec-cockpit-kb-confidential"
  (entra/create-acl-identities.sh:47-49)

- O script cria (invoca create_user para) dois usuários com os nicknames e display names:
  - "cockpit-test-a" — "Cockpit Test — Cleared (A)"
  - "cockpit-test-b" — "Cockpit Test — Public-only (B)"
  (entra/create-acl-identities.sh:51-52)

- O script adiciona o usuário A como membro dos três grupos e adiciona o usuário B ao grupo público; as chamadas usam `az ad group member add`. (entra/create-acl-identities.sh:54-55)

- O script imprime instruções e variáveis a serem colocadas em backend/.env, incluindo COCKPIT_ACL_PUBLIC_GROUP, COCKPIT_ACL_INTERNAL_GROUP, COCKPIT_ACL_CONFIDENTIAL_GROUP, COCKPIT_TEST_USER_A e COCKPIT_TEST_USER_B. (entra/create-acl-identities.sh:57-63)

- O comentário no script afirma que é idempotente ("Idempotent: re-running reuses existing groups/users."). (entra/create-acl-identities.sh:11-12)

- entra/create-test-users.sh é um script bash que se apresenta como "Phase 4 — create the two test identities ..." e inclui comentários descrevendo "User A" e "User B" e observações sobre uso/privilegios. (entra/create-test-users.sh:1-13)

- O script create-test-users.sh define DOMAIN e PW a partir dos parâmetros positionais e usa set -euo pipefail. (entra/create-test-users.sh:15-18)

- O script obtém os ids dos grupos públicos/internal/confidential via `az ad group show --group ... --query id -o tsv` usando a função gid e armazena em PUB, INT e CONF. (entra/create-test-users.sh:20-23)

- O script define create_user que chama `az ad user create` com --display-name, --user-principal-name "${1}@${DOMAIN}", --password "$PW" e --force-change-password-next-sign-in true, retornando o id. (entra/create-test-users.sh:25-31)

- O script cria os usuários "cockpit-test-a" e "cockpit-test-b" e adiciona o usuário A a PUB, INT e CONF e adiciona o usuário B a PUB usando `az ad group member add`. (entra/create-test-users.sh:34-38)

- O script imprime linhas de resumo com os ids de A, B e dos grupos. (entra/create-test-users.sh:40-42)

- main.parameters.json é um arquivo de parâmetros de implantação que declara os parâmetros: environmentName, location, principalId, principalType, searchLocation, entraTenantId, entraApiClientId, entraApiClientSecret, cada um com um "value" contendo uma referência a uma variável de ambiente (por exemplo "${AZURE_ENV_NAME}", "${ENTRA_API_CLIENT_SECRET}"). (main.parameters.json:4-12)

## Observações baseadas apenas nos arquivos
- Todas as afirmações acima são extraídas diretamente do conteúdo ou dos comentários dos arquivos fornecidos e estão citadas por arquivo e linhas correspondentes. Se desejar que eu gere a página "Provisionamento e Deploy" com seções específicas de procedimento (comandos a executar, ordem, pré-requisitos), indique quais seções quer incluir; eu só manterei conteúdo que puder ser diretamente ancorado nos arquivos fornecidos.