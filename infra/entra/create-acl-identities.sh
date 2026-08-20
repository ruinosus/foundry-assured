#!/usr/bin/env bash
# Phase 4 — PORTABLE identity bootstrap for document-level access control.
#
# Why a script and not (only) Bicep: creating directory objects (groups/users) goes
# through Microsoft Graph and needs *directory* rights (Groups/User Administrator) —
# NOT the tenant-scope ARM deployment rights that `az deployment tenant create` needs
# and that personal/low-privilege accounts lack. `az ad` calls Graph directly, so this
# works wherever you can manage your own directory, even without ARM tenant rights.
# (entra.bicep remains the full-IaC option for orgs whose pipeline identity has the
# tenant ARM + directory roles.)
#
# Idempotent: re-running reuses existing groups/users.
#
#   ./create-acl-identities.sh <tenant-domain>
#   e.g. ./create-acl-identities.sh jeffersonbarnabegmail.onmicrosoft.com
#
# A SENHA NÃO É ARGUMENTO. Ela é lida do stdin (sem eco) ou de $ACL_TEST_PASSWORD, porque
# argumento de linha de comando fica no histórico do shell e aparece em `ps` para qualquer
# processo da máquina enquanto o comando roda.

set -euo pipefail

DOMAIN="${1:?usage: create-acl-identities.sh <tenant-domain>}"
# Três formas de receber a senha, nenhuma delas por argumento (argumento vai para o histórico
# do shell e para o `ps` de qualquer processo da máquina):
#   1. $ACL_TEST_PASSWORD, quando já existe no ambiente;
#   2. stdin, quando não é terminal — `./script dominio < arquivo-de-senha`. É o caminho para
#      automação e para harnesses sem TTY, onde `read -rs` não recebe nada e o script sairia
#      sem criar ninguém;
#   3. prompt oculto, quando há terminal de verdade.
if [ -n "${ACL_TEST_PASSWORD:-}" ]; then
  PW="$ACL_TEST_PASSWORD"
elif [ ! -t 0 ]; then
  IFS= read -r PW || true
else
  printf 'Senha para as duas contas de teste (não aparece na tela): ' >&2
  read -rs PW; printf '\n' >&2
fi
PW="${PW%%[$'\r\n']*}"   # tolera arquivo terminado em newline
[ -n "$PW" ] || { echo "✖ senha vazia" >&2; exit 1; }

create_group() {  # displayName mailNickname -> objectId
  local id
  id=$(az ad group show --group "$2" --query id -o tsv 2>/dev/null || true)
  if [ -z "$id" ]; then
    id=$(az ad group create --display-name "$1" --mail-nickname "$2" --query id -o tsv)
    echo "  + grupo $1" >&2
  else
    echo "  = grupo $1 (já existe)" >&2
  fi
  echo "$id"
}

create_user() {  # nickname displayName -> objectId
  local id
  id=$(az ad user show --id "${1}@${DOMAIN}" --query id -o tsv 2>/dev/null || true)
  if [ -z "$id" ]; then
    # `--force-change-password-next-sign-in FALSE` é obrigatório aqui, não preferência: os
    # gates de segurança entram nessas contas por ROPC (`grant_type=password`), e uma conta que
    # exige troca no próximo login recusa esse fluxo. Com `true`, as contas nascem inúteis para
    # o CI — e o erro que aparece lá não menciona troca de senha, então custa caro descobrir.
    # São identidades de TESTE, sem privilégio, cuja senha vive num secret do repositório.
    id=$(az ad user create --display-name "$2" --user-principal-name "${1}@${DOMAIN}" \
      --password "$PW" --force-change-password-next-sign-in false --query id -o tsv)
    echo "  + usuário $1" >&2
  else
    echo "  = usuário $1 (já existe)" >&2
  fi
  echo "$id"
}

PUB=$(create_group "SEC-techdocs-kb-public" "sec-techdocs-kb-public")
INT=$(create_group "SEC-techdocs-kb-internal" "sec-techdocs-kb-internal")
CONF=$(create_group "SEC-techdocs-kb-confidential" "sec-techdocs-kb-confidential")

A=$(create_user "techdocs-test-a" "TechDocs Test — Cleared (A)")
B=$(create_user "techdocs-test-b" "TechDocs Test — Public-only (B)")

for g in "$PUB" "$INT" "$CONF"; do az ad group member add --group "$g" --member-id "$A" 2>/dev/null || true; done
az ad group member add --group "$PUB" --member-id "$B" 2>/dev/null || true

# A audiência de leitura do selfwiki é OUTRO grupo (o do app), e o verificador do
# `ingest-selfwiki` consulta o índice COMO o usuário A — se A não estiver aqui, a busca devolve
# zero, o fail-closed funciona como projetado e o gate reprova por falta de membresia, não por
# falta de carimbo. Duas causas, um sintoma. Fica no script porque como passo manual seria
# esquecido no primeiro ambiente novo.
#
# B fica DE FORA de propósito: é a identidade que prova que o trim discrimina por pessoa. Se B
# passar a enxergar, o controle de acesso quebrou.
APP_USERS=$(az ad group show --group "foundry-assured-app-users" --query id -o tsv 2>/dev/null || true)
if [ -n "$APP_USERS" ]; then
  az ad group member add --group "$APP_USERS" --member-id "$A" 2>/dev/null || true
  echo "  = A adicionado à audiência do selfwiki (foundry-assured-app-users)" >&2
else
  echo "  ⚠ grupo foundry-assured-app-users não encontrado — o gate do selfwiki vai reprovar" >&2
fi

echo ""
echo "# Cole no backend/.env (e no ACL_GROUPS do ingest):"
echo "ACL_PUBLIC_GROUP=$PUB"
echo "ACL_INTERNAL_GROUP=$INT"
echo "ACL_CONFIDENTIAL_GROUP=$CONF"
# UPN, NÃO object id: o código usa estas duas variáveis como `username` do fluxo ROPC
# (eval/access_control_test.py: `upn_a = os.environ[...]` → `_ropc_token(upn_a, ...)`).
# Object id ali dentro faz o login falhar com "usuário inválido" — erro que não aponta para cá.
echo "TECHDOCS_TEST_USER_A=techdocs-test-a@${DOMAIN}   # public+internal+confidential"
echo "TECHDOCS_TEST_USER_B=techdocs-test-b@${DOMAIN}   # public only"
echo ""
echo "# object ids (para az ad group member add, NÃO para as variáveis acima): A=$A B=$B"
