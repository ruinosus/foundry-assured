# Fatos extraídos dos arquivos fornecidos

## Arquivos enviados
- entra/create-test-users.sh (fornecido)  
- main.parameters.json (fornecido)

---

## entra/create-test-users.sh — fatos observáveis
- É um script Bash (linha shebang presentem). (entra/create-test-users.sh)  
- Os comentários descrevem o objetivo: criar duas identidades de teste e colocá‑las nos grupos de "classification-tier" (entrando em entra.bicep) — “User A — cleared for ALL tiers (public + internal + confidential)” e “User B — cleared for public ONLY (must never retrieve a confidential doc)”. (entra/create-test-users.sh)  
- O script espera dois argumentos: <tenant-domain> e <initial-password>, conforme as variáveis DOMAIN e PW e o comentário de uso/exemplo no arquivo. (entra/create-test-users.sh)  
- O script define uma função gid que obtém o id de um grupo com `az ad group show --group "$1" --query id -o tsv`. (entra/create-test-users.sh)  
- O script obtém IDs dos grupos chamados `SEC-cockpit-kb-public`, `SEC-cockpit-kb-internal` e `SEC-cockpit-kb-confidential` usando a função gid. (entra/create-test-users.sh)  
- Há uma função create_user que chama `az ad user create` com os parâmetros `--display-name`, `--user-principal-name`, `--password`, `--force-change-password-next-sign-in true` e `--query id -o tsv`. (entra/create-test-users.sh)  
- O script cria dois usuários com os nomes de conta (user principal names) `cockpit-test-a@<DOMAIN>` e `cockpit-test-b@<DOMAIN>` e com os display names `Cockpit Test — Cleared (A)` e `Cockpit Test — Public-only (B)`, e captura os seus objectIds nas variáveis A e B. (entra/create-test-users.sh)  
- O script adiciona o usuário A (variável A) como membro de todos os três grupos (public, internal, confidential) e adiciona o usuário B (variável B) apenas ao grupo public, usando `az ad group member add`. (entra/create-test-users.sh)  
- No final o script imprime mensagens informando os objectIds de A e B e os IDs dos grupos; as mensagens indicam “A → public + internal + confidential” e “B → public only”. (entra/create-test-users.sh)  
- Os comentários indicam que o script requer o Azure CLI autenticado com permissões para criar usuários e gerenciar membros de grupo (User Administrator + Groups Administrator). (entra/create-test-users.sh)

---

## main.parameters.json — fatos observáveis
- É um arquivo JSON contendo as chaves `$schema` e `contentVersion` no topo. (main.parameters.json)  
- Define um objeto `parameters` que contém as entradas: `environmentName`, `location`, `principalId`, `principalType`, `searchLocation`, `entraTenantId`, `entraApiClientId` e `entraApiClientSecret`. (main.parameters.json)  
- Cada parâmetro tem um campo `value` cujo conteúdo é uma string placeholder no formato `${...}` (por exemplo `"${AZURE_ENV_NAME}"`). (main.parameters.json)

---

Nada mais foi incluído — o conteúdo acima está estritamente limitado ao que consta nos arquivos fornecidos.