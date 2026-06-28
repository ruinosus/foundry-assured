---
title: "Identidades e Controle de Acesso (ACL)"
description: "Documentação do bootstrap de identidades e grupos (fatos extraídos dos arquivos fonte)."
---

## Visão geral — fatos extraídos dos arquivos fonte

- O repositório inclui um script Bash `entra/create-acl-identities.sh` que cria ou reutiliza grupos e usuários no Azure AD usando comandos `az ad`. (entra/create-acl-identities.sh:1-63)
- O script declara ser idempotente: re-execuções reaproveitam grupos/usuários existentes conforme comentário no cabeçalho. (entra/create-acl-identities.sh:8-10, entra/create-acl-identities.sh:12)
- Há um arquivo `entra/bicepconfig.json` que declara configurações relacionadas ao Bicep, incluindo uma entrada para `microsoftGraphV1`. (entra/bicepconfig.json:1-6)

## Como executar (uso reproduzido do script)

- Sintaxe esperada pelo script: `./create-acl-identities.sh <tenant-domain> <initial-password>`. (entra/create-acl-identities.sh:12-13)
- O script valida a presença dos dois argumentos e usa as variáveis `DOMAIN` e `PW` internamente. (entra/create-acl-identities.sh:15-16, entra/create-acl-identities.sh:18-19)
- O script ativa `set -euo pipefail` no início. (entra/create-acl-identities.sh:15)

## O que o script faz — pontos observáveis no código

- Define a função `create_group()` que:
  - tenta obter o id do grupo com `az ad group show --group "$2" --query id -o tsv` (stderr redirecionado para /dev/null e tolerância a erro via `|| true`). (entra/create-acl-identities.sh:22-25)
  - se não encontrar, cria o grupo com `az ad group create --display-name "$1" --mail-nickname "$2" --query id -o tsv`. (entra/create-acl-identities.sh:25-27)
  - escreve mensagens de log para stderr indicando criação ou existência e retorna o `id`. (entra/create-acl-identities.sh:26-31)

- Define a função `create_user()` que:
  - tenta obter o id do usuário com `az ad user show --id "${1}@${DOMAIN}" --query id -o tsv`. (entra/create-acl-identities.sh:34-36)
  - se não existir, cria o usuário com `az ad user create --display-name "$2" --user-principal-name "${1}@${DOMAIN}" --password "$PW" --force-change-password-next-sign-in true --query id -o tsv`. (entra/create-acl-identities.sh:37-39)
  - escreve mensagens de log para stderr indicando criação ou existência e retorna o `id`. (entra/create-acl-identities.sh:39-45)

- Cria/obtém três grupos, atribuindo-os às variáveis `PUB`, `INT`, `CONF` com estes argumentos passados à `create_group`:
  - ("SEC-cockpit-kb-public", "sec-cockpit-kb-public")
  - ("SEC-cockpit-kb-internal", "sec-cockpit-kb-internal")
  - ("SEC-cockpit-kb-confidential", "sec-cockpit-kb-confidential") (entra/create-acl-identities.sh:47-49)

- Cria/obtém dois usuários de teste, atribuindo-os às variáveis `A` e `B` com estes argumentos passados à `create_user`:
  - ("cockpit-test-a", "Cockpit Test — Cleared (A)")
  - ("cockpit-test-b", "Cockpit Test — Public-only (B)") (entra/create-acl-identities.sh:51-52)

- Associa membros:
  - adiciona o usuário representado por `A` como membro de cada um dos grupos `PUB`, `INT`, `CONF` no loop `for` (usando `az ad group member add --group "$g" --member-id "$A"`, com tolerância a erro `|| true`). (entra/create-acl-identities.sh:53-55)
  - adiciona o usuário representado por `B` como membro do grupo `PUB` (uso de `az ad group member add --group "$PUB" --member-id "$B" || true`). (entra/create-acl-identities.sh:55)

- Saída/print final:
  - o script imprime ao final linhas indicando onde colar os valores e as variáveis com os IDs: `COCKPIT_ACL_PUBLIC_GROUP`, `COCKPIT_ACL_INTERNAL_GROUP`, `COCKPIT_ACL_CONFIDENTIAL_GROUP`, `COCKPIT_TEST_USER_A`, `COCKPIT_TEST_USER_B`. (entra/create-acl-identities.sh:57-63)
  - o texto impresso inclui a instrução literal: "# Cole no backend/.env (e no COCKPIT_ACL_GROUPS do ingest):" seguida das linhas das variáveis. (entra/create-acl-identities.sh:57-63)

## Observações sobre o cabeçalho do script e o bicepconfig.json (texto literal do código)

- O cabeçalho do script contém um comentário explicando que a criação de objetos de diretório (grupos/usuários) passa pelo Microsoft Graph e que o script usa `az ad` para operar diretamente contra o Graph quando a conta tiver os direitos necessários; o comentário contrasta esse fluxo com direitos de deployment ARM de tenant referidos no texto do próprio cabeçalho. (entra/create-acl-identities.sh:4-10)

- Em `entra/bicepconfig.json` há as chaves:
  - "experimentalFeaturesEnabled": { "extensibility": true } (entra/bicepconfig.json:2-3)
  - "extensions": { "microsoftGraphV1": "br:mcr.microsoft.com/bicep/extensions/microsoftgraph/v1.0:0.1.8-preview" } (entra/bicepconfig.json:4-6)

## Arquivos fornecidos (fontes citadas)

- entra/create-acl-identities.sh (linhas citadas acima). (entra/create-acl-identities.sh:1-63)
- entra/bicepconfig.json (linhas citadas acima). (entra/bicepconfig.json:1-6)

