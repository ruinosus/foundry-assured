#!/usr/bin/env bash
# Assign the app's **Admin** role to a user via Microsoft Graph — so the HITL approval card and the
# /admin/users portal work without the manual "Enterprise applications → Users and groups" portal click.
# Defaults to the SIGNED-IN user. Idempotent (a 409 = already assigned). Run after setup-app-roles.sh.
#
# Usage (repo root):
#   ./scripts/assign-admin-role.sh                 # assign Admin to yourself (signed-in user)
#   ./scripts/assign-admin-role.sh user@tenant.com # assign Admin to a specific UPN / object id
#   ENTRA_API_CLIENT_ID=<api-app-id> ./scripts/assign-admin-role.sh   # explicit API app
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

API_ID="${ENTRA_API_CLIENT_ID:-$(sed -n 's/^ENTRA_API_CLIENT_ID=\(.*\)$/\1/p' "$ROOT/apps/backend/.env" 2>/dev/null | head -1)}"
[ -z "${API_ID:-}" ] && { echo "✖ ENTRA_API_CLIENT_ID not set (run scripts/setup-entra.sh first)"; exit 1; }

# resolve the target user → object id (default: signed-in user)
TARGET="${1:-$(az ad signed-in-user show --query id -o tsv)}"
case "$TARGET" in *@*) TARGET="$(az ad user show --id "$TARGET" --query id -o tsv)";; esac
[ -z "${TARGET:-}" ] && { echo "✖ could not resolve the target user object id"; exit 1; }

# the API app's service principal + its 'Admin' appRole id
SP_ID="$(az ad sp show --id "$API_ID" --query id -o tsv 2>/dev/null || true)"
[ -z "$SP_ID" ] && { echo "✖ no service principal for API app $API_ID"; exit 1; }
ADMIN_ROLE_ID="$(az ad sp show --id "$API_ID" --query "appRoles[?value=='Admin'].id | [0]" -o tsv 2>/dev/null || true)"
[ -z "$ADMIN_ROLE_ID" ] && { echo "✖ no 'Admin' appRole on the API app (run scripts/setup-app-roles.sh first)"; exit 1; }

if az rest --method POST \
     --url "https://graph.microsoft.com/v1.0/users/$TARGET/appRoleAssignments" \
     --headers "Content-Type=application/json" \
     --body "{\"principalId\":\"$TARGET\",\"resourceId\":\"$SP_ID\",\"appRoleId\":\"$ADMIN_ROLE_ID\"}" \
     >/dev/null 2>&1; then
  echo "  ✓ Admin role assigned to $TARGET"
else
  echo "  · Admin role already assigned to $TARGET (or needs admin consent)"
fi
