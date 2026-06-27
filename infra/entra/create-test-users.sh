#!/usr/bin/env bash
# Phase 4 — create the two test identities that prove query-time ACL trimming, and
# place them in the classification-tier groups (created by entra.bicep).
#
#   User A — cleared for ALL tiers (public + internal + confidential)
#   User B — cleared for public ONLY (must never retrieve a confidential doc)
#
# Users carry an initial password, so they live in a script (with a secure param),
# not in IaC. Run after deploying entra.bicep. Requires az CLI logged in with rights
# to create users and manage group membership (User Administrator + Groups Administrator).
#
#   ./create-test-users.sh <tenant-domain> <initial-password>
#   e.g. ./create-test-users.sh contoso.onmicrosoft.com 'Str0ng-Passw0rd!'

set -euo pipefail

DOMAIN="${1:?usage: create-test-users.sh <tenant-domain> <initial-password>}"
PW="${2:?initial password required}"

gid() { az ad group show --group "$1" --query id -o tsv; }
PUB=$(gid "SEC-cockpit-kb-public")
INT=$(gid "SEC-cockpit-kb-internal")
CONF=$(gid "SEC-cockpit-kb-confidential")

create_user() {  # nickname displayname -> prints objectId
  az ad user create \
    --display-name "$2" \
    --user-principal-name "${1}@${DOMAIN}" \
    --password "$PW" \
    --force-change-password-next-sign-in true \
    --query id -o tsv
}

A=$(create_user "cockpit-test-a" "Cockpit Test — Cleared (A)")
B=$(create_user "cockpit-test-b" "Cockpit Test — Public-only (B)")

for g in "$PUB" "$INT" "$CONF"; do az ad group member add --group "$g" --member-id "$A"; done
az ad group member add --group "$PUB" --member-id "$B"

echo "✅ A=$A  → public + internal + confidential"
echo "✅ B=$B  → public only"
echo "Groups: public=$PUB internal=$INT confidential=$CONF"
