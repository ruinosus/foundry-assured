# Fatos extraídos dos arquivos fornecidos

- entra/bicepconfig.json
  - Define "experimentalFeaturesEnabled" com "extensibility": true. (entra/bicepconfig.json)
  - Registra uma extensão "microsoftGraphV1" com o valor "br:mcr.microsoft.com/bicep/extensions/microsoftgraph/v1.0:0.1.8-preview". (entra/bicepconfig.json)

- entra/create-acl-identities.sh
  - É um script Bash (shebang "#!/usr/bin/env bash") e habilita "set -euo pipefail". (entra/create-acl-identities.sh)
  - Contém a descrição "Phase 4 — PORTABLE identity bootstrap for document-level access control." como comentário no topo. (entra/create-acl-identities.sh)
  - Contém comentários explicando que a criação de objetos de diretório (grupos/usuários) passa pelo Microsoft Graph e precisa de direitos de diretório (Groups/User Administrator), enquanto implantações ARM a nível de locatário exigem outras permissões; e que "az ad" chama o Graph diretamente. (entra/create-acl-identities.sh)
  - Implementa as funções create_group e create_user que usam comandos az ad group show/create e az ad user show/create para obter ou criar objetos, tornando a operação idempotente conforme comentários. (entra/create-acl-identities.sh)
  - Cria/garante a existência dos grupos com display names "SEC-cockpit-kb-public", "SEC-cockpit-kb-internal" e "SEC-cockpit-kb-confidential" e mail nicknames correspondentes "sec-cockpit-kb-public", "sec-cockpit-kb-internal", "sec-cockpit-kb-confidential". (entra/create-acl-identities.sh)
  - Cria/garante os usuários "cockpit-test-a" (display name "Cockpit Test — Cleared (A)") e "cockpit-test-b" (display name "Cockpit Test — Public-only (B)") e adiciona "cockpit-test-a" a todos os três grupos e "cockpit-test-b" apenas ao grupo público, usando az ad group member add. (entra/create-acl-identities.sh)
  - Ao final, imprime recomendações de variáveis de ambiente para colar em backend/.env, incluindo COCKPIT_ACL_PUBLIC_GROUP, COCKPIT_ACL_INTERNAL_GROUP, COCKPIT_ACL_CONFIDENTIAL_GROUP, COCKPIT_TEST_USER_A e COCKPIT_TEST_USER_B. (entra/create-acl-identities.sh)

- entra/create-test-users.sh
  - É um script Bash (shebang "#!/usr/bin/env bash") e habilita "set -euo pipefail". (entra/create-test-users.sh)
  - Contém a descrição "Phase 4" e comentários que definem dois usuários de teste: "User A — cleared for ALL tiers (public + internal + confidential)" e "User B — cleared for public ONLY". (entra/create-test-users.sh)
  - Indica, em comentário, que deve ser executado após implantar entra.bicep e que requer az CLI autenticado com direitos para criar usuários e gerenciar associação de grupos (User Administrator + Groups Administrator). (entra/create-test-users.sh)
  - Obtém IDs dos grupos "SEC-cockpit-kb-public", "SEC-cockpit-kb-internal" e "SEC-cockpit-kb-confidential" via az ad group show, cria os dois usuários via az ad user create, adiciona o usuário A a todos os três grupos e o usuário B apenas ao grupo público, e imprime as IDs/resultados. (entra/create-test-users.sh)