#!/usr/bin/env bash
# Declare the app's RBAC roles + grant the app-only Graph permissions the admin portal needs.
# Run ONCE per tenant by someone who can admin-consent (you're the admin). Idempotent: the
# appRole ids are fixed, so re-running replaces the set in place without orphaning assignments.
#
#   ENTRA_API_CLIENT_ID=<api-app-client-id> ./scripts/setup-app-roles.sh
#
# Needs: az login. See docs/RBAC-AND-USER-MANAGEMENT-PLAN.md + docs/IDENTITY-AND-ACCESS-SETUP.md.
set -euo pipefail

APP="${ENTRA_API_CLIENT_ID:-${1:-}}"
[ -n "$APP" ] || { echo "Set ENTRA_API_CLIENT_ID (the API app registration's client id) or pass it as \$1."; exit 1; }
GRAPH_APPID="00000003-0000-0000-c000-000000000000"  # Microsoft Graph (stable, well-known)

echo "== App roles (Admin / Author / Approver / Reader) on app $APP =="
# Fixed ids → idempotent. allowedMemberTypes:["User"] = assignable to users (and to groups
# once the tenant has Entra ID P1 — same array, no change needed here).
az ad app update --id "$APP" --app-roles '[
  {"allowedMemberTypes":["User"],"displayName":"Admin","value":"Admin","id":"3f2a7b10-1c4e-4b9a-9f01-aa0000000001","isEnabled":true,"description":"Manage users and role assignments, configure, ingest KBs."},
  {"allowedMemberTypes":["User"],"displayName":"Author","value":"Author","id":"3f2a7b10-1c4e-4b9a-9f01-aa0000000002","isEnabled":true,"description":"Generate/upload content (decks, wikis) and trigger ingest."},
  {"allowedMemberTypes":["User"],"displayName":"Approver","value":"Approver","id":"3f2a7b10-1c4e-4b9a-9f01-aa0000000003","isEnabled":true,"description":"Approve/reject HITL escalations (the create_ticket approval)."},
  {"allowedMemberTypes":["User"],"displayName":"Reader","value":"Reader","id":"3f2a7b10-1c4e-4b9a-9f01-aa0000000004","isEnabled":true,"description":"Query the agents and see entitled content."}
]'
echo "  ✓ app roles declared"

echo "== App-only Microsoft Graph permissions =="
# Resolve each permission's GUID LIVE from the Graph service principal (don't hardcode ids).
for PERM in User.ReadWrite.All User.Invite.All AppRoleAssignment.ReadWrite.All Directory.Read.All; do
  PID=$(az ad sp show --id "$GRAPH_APPID" --query "appRoles[?value=='$PERM'].id | [0]" -o tsv)
  [ -n "$PID" ] || { echo "  ! could not resolve $PERM"; continue; }
  az ad app permission add --id "$APP" --api "$GRAPH_APPID" --api-permissions "$PID=Role" >/dev/null
  echo "  ✓ added $PERM ($PID)"
done

echo "== Admin consent (interactive — needs a Privileged Role / Global admin) =="
az ad app permission admin-consent --id "$APP" && echo "  ✓ consent granted" \
  || echo "  ! admin-consent failed — grant it in the portal: Entra ID → App registrations → $APP → API permissions → Grant admin consent"

echo ""
echo "Done. Now assign yourself the Admin role:"
echo "  Entra ID → Enterprise applications → (the API app) → Users and groups → Add → you → Admin"
echo "Then sign out/in so your token carries the 'roles' claim."
