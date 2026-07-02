#!/usr/bin/env bash
# Automates docs/DEPLOYMENT.md › Step 3 — the two Entra app registrations for
# sign-in + On-Behalf-Of (the fiddliest, most error-prone part). Idempotent:
# re-running reuses existing apps (matched by display name) and rewrites the env.
#
# Creates:
#   • API app  — audience of incoming tokens; exposes api://<id>/access_as_user,
#     token v2, a client secret, and the delegated perms the OBO exchange needs.
#   • SPA app  — the browser sign-in; redirect http://localhost:3000 + access_as_user.
# Then writes ENTRA_* into apps/backend/.env and NEXT_PUBLIC_* into apps/frontend/.env.local.
#
# Requires: az login as someone who can create app registrations AND grant admin
# consent (Application/Cloud Application Administrator). If consent fails, the script
# tells you which app to consent in the portal — everything else still applies.
#
# Usage (repo root):  ./scripts/setup-entra.sh
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACK_ENV="$ROOT/apps/backend/.env"
FRONT_ENV="$ROOT/apps/frontend/.env.local"
API_NAME="${API_NAME:-foundry-helpdesk-api}"
SPA_NAME="${SPA_NAME:-foundry-helpdesk-spa}"
REDIRECT="${REDIRECT:-http://localhost:3000}"

# Well-known first-party resource the Foundry data plane is fronted by (ai.azure.com).
AML_APPID="18a66f5f-dbdf-4c17-9dd7-1634712a9cbe"

command -v az >/dev/null || { echo "✖ az not found."; exit 1; }
command -v uuidgen >/dev/null || { echo "✖ uuidgen not found."; exit 1; }
TENANT="$(az account show --query tenantId -o tsv)" || { echo "✖ Run 'az login' first."; exit 1; }
GRAPH="https://graph.microsoft.com/v1.0/applications"

upsert() { # FILE KEY VALUE
  local file="$1" key="$2" value="$3"; touch "$file"
  if grep -qE "^$key=" "$file"; then
    awk -v k="$key" -v v="$value" -F= 'BEGIN{OFS="="} $1==k{$0=k"="v} {print}' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
  else echo "$key=$value" >> "$file"; fi
}
ensure_app() { # DISPLAY_NAME -> echoes "objectId appId"
  local name="$1" objid appid
  objid="$(az ad app list --display-name "$name" --query "[0].id" -o tsv 2>/dev/null)"
  if [ -z "$objid" ]; then
    # list projection (not a hash) so the two columns keep their order in tsv
    read -r objid appid < <(az ad app create --display-name "$name" --query "[id,appId]" -o tsv)
  else
    appid="$(az ad app show --id "$objid" --query appId -o tsv)"
  fi
  echo "$objid $appid"
}
# user_impersonation delegated scope id of a resource app (resolved, not hardcoded).
res_scope() { az ad sp show --id "$1" --query "oauth2PermissionScopes[?value=='user_impersonation'].id | [0]" -o tsv 2>/dev/null; }

echo "▸ Tenant: $TENANT"

# ---- API app ---------------------------------------------------------------
echo "▸ API app ($API_NAME)…"
read -r API_OBJID API_APPID < <(ensure_app "$API_NAME")
echo "  appId: $API_APPID"

# Reuse an existing access_as_user scope id if present, else mint one.
SCOPE_ID="$(az ad app show --id "$API_OBJID" --query "api.oauth2PermissionScopes[?value=='access_as_user'].id | [0]" -o tsv 2>/dev/null)"
if [ -z "$SCOPE_ID" ]; then
  SCOPE_ID="$(uuidgen | tr 'A-Z' 'a-z')"
  az rest --method PATCH --url "$GRAPH/$API_OBJID" --headers "Content-Type=application/json" --body "$(cat <<JSON
{"identifierUris":["api://$API_APPID"],
 "api":{"requestedAccessTokenVersion":2,
  "oauth2PermissionScopes":[{"id":"$SCOPE_ID","value":"access_as_user","type":"User","isEnabled":true,
   "adminConsentDisplayName":"Access as user","adminConsentDescription":"Access the API as the signed-in user",
   "userConsentDisplayName":"Access as user","userConsentDescription":"Access the API on your behalf"}]}}
JSON
)"
  echo "  ✔ exposed api://$API_APPID/access_as_user + token v2"
else
  az rest --method PATCH --url "$GRAPH/$API_OBJID" --headers "Content-Type=application/json" \
    --body "{\"identifierUris\":[\"api://$API_APPID\"],\"api\":{\"requestedAccessTokenVersion\":2}}"
  echo "  ✔ scope already present (reused)"
fi

# Client secret (always append a fresh one so .env has a valid value).
API_SECRET="$(az ad app credential reset --id "$API_OBJID" --append --display-name bootstrap --years 1 --query password -o tsv)"
echo "  ✔ client secret minted"

# Delegated perms the OBO exchange needs: AML (ai.azure.com) + Search (search.azure.com).
SEARCH_APPID="$(az ad sp list --filter "servicePrincipalNames/any(x:x eq 'https://search.azure.com')" --query "[0].appId" -o tsv --all 2>/dev/null || true)"
for res in "$AML_APPID" "$SEARCH_APPID"; do
  [ -z "$res" ] && { echo "  ⚠ could not resolve a resource app (search.azure.com?) — add its delegated user_impersonation in the portal"; continue; }
  sid="$(res_scope "$res")"
  [ -z "$sid" ] && { echo "  ⚠ no user_impersonation scope on $res — add it in the portal"; continue; }
  az ad app permission add --id "$API_APPID" --api "$res" --api-permissions "$sid=Scope" 2>/dev/null && echo "  ✔ delegated perm on $res"
done

# ---- SPA app ---------------------------------------------------------------
echo "▸ SPA app ($SPA_NAME)…"
read -r SPA_OBJID SPA_APPID < <(ensure_app "$SPA_NAME")
echo "  appId: $SPA_APPID"
az rest --method PATCH --url "$GRAPH/$SPA_OBJID" --headers "Content-Type=application/json" \
  --body "{\"spa\":{\"redirectUris\":[\"$REDIRECT\"]}}"
echo "  ✔ SPA redirect $REDIRECT"
az ad app permission add --id "$SPA_APPID" --api "$API_APPID" --api-permissions "$SCOPE_ID=Scope" 2>/dev/null && echo "  ✔ SPA → access_as_user"

# Register the SPA as a KNOWN CLIENT of the API app. This is what makes the multi-tier On-Behalf-Of
# chain work in the browser: SPA token → API (audience) → OBO → ai.azure.com (Foundry inference) /
# search.azure.com. Without it, the OBO of a SPA-issued token to the downstream resource fails/returns
# a token that 403s on inference — even though the API app already holds the delegated permission and
# admin consent (verified: a direct API-app token OBO's fine; only the SPA-originated chain breaks).
# Consent granted to the SPA then cascades to the API's downstream permissions (combined consent).
az rest --method PATCH --url "$GRAPH/$API_OBJID" --headers "Content-Type=application/json" \
  --body "{\"api\":{\"knownClientApplications\":[\"$SPA_APPID\"]}}" 2>/dev/null \
  && echo "  ✔ SPA registered as known client of the API (enables SPA→API→downstream OBO)"

# ---- Admin consent (needs a privileged role; non-fatal if it fails) --------
echo "▸ Granting admin consent…"
az ad app permission admin-consent --id "$API_APPID" 2>/dev/null && echo "  ✔ API consented" \
  || echo "  ⚠ consent the API app in the portal (Entra → $API_NAME → API permissions → Grant admin consent)"
az ad app permission admin-consent --id "$SPA_APPID" 2>/dev/null && echo "  ✔ SPA consented" \
  || echo "  ⚠ consent the SPA app in the portal (Entra → $SPA_NAME → API permissions → Grant admin consent)"

# ---- Write env -------------------------------------------------------------
echo "▸ Writing env files…"
upsert "$BACK_ENV"  ENTRA_TENANT_ID         "$TENANT"
upsert "$BACK_ENV"  ENTRA_API_CLIENT_ID     "$API_APPID"
upsert "$BACK_ENV"  ENTRA_API_CLIENT_SECRET "$API_SECRET"
upsert "$BACK_ENV"  ENTRA_SPA_CLIENT_ID     "$SPA_APPID"
upsert "$FRONT_ENV" NEXT_PUBLIC_ENTRA_TENANT_ID    "$TENANT"
upsert "$FRONT_ENV" NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID "$SPA_APPID"
upsert "$FRONT_ENV" NEXT_PUBLIC_ENTRA_API_CLIENT_ID "$API_APPID"

cat <<EOF

✅ Entra configured. The app now requires sign-in locally.
   • Start the app on port 3000 (must match the SPA redirect).
   • After deploying, add the deployed WEB_URL as a SPA redirect URI:
       az rest --method PATCH --url "$GRAPH/$SPA_OBJID" \\
         --headers "Content-Type=application/json" \\
         --body '{"spa":{"redirectUris":["$REDIRECT","https://<your-web-fqdn>"]}}'
EOF
