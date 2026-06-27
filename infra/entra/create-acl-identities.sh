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
#   ./create-acl-identities.sh <tenant-domain> <initial-password>
#   e.g. ./create-acl-identities.sh jeffersonbarnabegmail.onmicrosoft.com 'Str0ng-Pw!2026'

set -euo pipefail

DOMAIN="${1:?usage: create-acl-identities.sh <tenant-domain> <initial-password>}"
PW="${2:?initial password required}"

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
    id=$(az ad user create --display-name "$2" --user-principal-name "${1}@${DOMAIN}" \
      --password "$PW" --force-change-password-next-sign-in true --query id -o tsv)
    echo "  + usuário $1" >&2
  else
    echo "  = usuário $1 (já existe)" >&2
  fi
  echo "$id"
}

PUB=$(create_group "SEC-cockpit-kb-public" "sec-cockpit-kb-public")
INT=$(create_group "SEC-cockpit-kb-internal" "sec-cockpit-kb-internal")
CONF=$(create_group "SEC-cockpit-kb-confidential" "sec-cockpit-kb-confidential")

A=$(create_user "cockpit-test-a" "Cockpit Test — Cleared (A)")
B=$(create_user "cockpit-test-b" "Cockpit Test — Public-only (B)")

for g in "$PUB" "$INT" "$CONF"; do az ad group member add --group "$g" --member-id "$A" 2>/dev/null || true; done
az ad group member add --group "$PUB" --member-id "$B" 2>/dev/null || true

echo ""
echo "# Cole no backend/.env (e no COCKPIT_ACL_GROUPS do ingest):"
echo "COCKPIT_ACL_PUBLIC_GROUP=$PUB"
echo "COCKPIT_ACL_INTERNAL_GROUP=$INT"
echo "COCKPIT_ACL_CONFIDENTIAL_GROUP=$CONF"
echo "COCKPIT_TEST_USER_A=$A   # public+internal+confidential"
echo "COCKPIT_TEST_USER_B=$B   # public only"
