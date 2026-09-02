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

# Well-known first-party resources the Foundry data plane is fronted by. It is NOT a single
# audience: project/KB operations go to ai.azure.com (AML), but MODEL INFERENCE goes to
# cognitiveservices.azure.com. Missing the latter still lets a request reach the backend and
# retrieve — then the model call 403s, because OBO can't mint a token for an audience the app
# never requested. Both are required.
AML_APPID="18a66f5f-dbdf-4c17-9dd7-1634712a9cbe"
COGSVC_APPID="7d312290-28c8-473c-a0ed-8e53749b6d6d"
AZURE_DEVOPS_APPID="499b84ac-1321-427f-aa17-267ca6975798"

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
  # Emit the SECURITY GROUP claim. Not cosmetic: per-document ACL is enforced by Azure AI Search,
  # which "extracts the user, group, and scope claims from the token" (learn.microsoft.com,
  # search-query-access-control-rbac-enforcement). Without this the token carries no `groups`, the
  # user belongs to nothing as far as Search is concerned, and every ACL'd document is trimmed away.
  #
  # The failure is silent and expensive: retrieval returns ZERO documents, the agent answers "no
  # authorized documents found", and nothing logs an error — fail-closed behaving correctly on
  # missing information. It cost an hour to find, and the fix is this one line.
  #
  # Caveat worth knowing: a user in more than ~150 groups gets an overage claim (a pointer, not the
  # list) and the trim stops working. Not a concern at this scale; it would be at enterprise scale.
  az rest --method PATCH --url "$GRAPH/$objid" --headers "Content-Type=application/json" \
    --body '{"groupMembershipClaims":"SecurityGroup"}' 2>/dev/null \
    && echo "  ✔ group claim (SecurityGroup) — required by the per-document ACL" >&2
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

# Delegated perms the OBO exchange needs: AML (ai.azure.com) + Cognitive Services
# (cognitiveservices.azure.com — model inference) + Search (search.azure.com).
SEARCH_APPID="$(az ad sp list --filter "servicePrincipalNames/any(x:x eq 'https://search.azure.com')" --query "[0].appId" -o tsv --all 2>/dev/null || true)"
for res in "$AML_APPID" "$COGSVC_APPID" "$SEARCH_APPID"; do
  [ -z "$res" ] && { echo "  ⚠ could not resolve a resource app (search.azure.com?) — add its delegated user_impersonation in the portal"; continue; }
  sid="$(res_scope "$res")"
  [ -z "$sid" ] && { echo "  ⚠ no user_impersonation scope on $res — add it in the portal"; continue; }
  # `permission add` APPENDS unconditionally — re-running this script would stack duplicate
  # entries for the same scope. Skip when it's already registered so the script stays idempotent.
  if az ad app show --id "$API_APPID" --query "requiredResourceAccess[?resourceAppId=='$res'].resourceAccess[].id" -o tsv 2>/dev/null | grep -qx "$sid"; then
    echo "  · delegated perm on $res (already present)"
  else
    az ad app permission add --id "$API_APPID" --api "$res" --api-permissions "$sid=Scope" 2>/dev/null && echo "  ✔ delegated perm on $res"
  fi
done

# Azure DevOps publication uses OBO with one delegated permission. `/.default` mints every
# statically registered scope for this resource, so merely adding vso.code_write is not enough:
# fail closed when a reused app registration carries any broader Azure DevOps permission.
AZURE_DEVOPS_SCOPE_ID="$(az ad sp show --id "$AZURE_DEVOPS_APPID" \
  --query "oauth2PermissionScopes[?value=='vso.code_write'].id | [0]" -o tsv 2>/dev/null || true)"
if [ -z "$AZURE_DEVOPS_SCOPE_ID" ]; then
  echo "  ✖ Azure DevOps delegated scope vso.code_write could not be resolved"
  exit 1
fi
AZURE_DEVOPS_REGISTERED_IDS="$(az ad app show --id "$API_APPID" \
  --query "requiredResourceAccess[?resourceAppId=='$AZURE_DEVOPS_APPID'].resourceAccess[].id" \
  -o tsv 2>/dev/null || true)"
if ! bash "$ROOT/scripts/validate-azure-devops-permissions.sh" \
  "$AZURE_DEVOPS_SCOPE_ID" "$AZURE_DEVOPS_REGISTERED_IDS"; then
  echo "  ✖ API app has Azure DevOps permissions beyond vso.code_write; remove them before continuing"
  exit 1
fi
if printf '%s\n' "$AZURE_DEVOPS_REGISTERED_IDS" | grep -Fqx "$AZURE_DEVOPS_SCOPE_ID"; then
  echo "  · delegated Azure DevOps vso.code_write (already present)"
else
  az ad app permission add --id "$API_APPID" --api "$AZURE_DEVOPS_APPID" \
    --api-permissions "$AZURE_DEVOPS_SCOPE_ID=Scope" 2>/dev/null
  echo "  ✔ delegated Azure DevOps vso.code_write"
fi

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

# ---- Audience group for the per-document ACL --------------------------------
# The selfwiki is a single-audience knowledge base: everyone with app access may read it. That
# audience is a security group, and its object id has to reach the backend as APP_USERS_GROUP_ID.
#
# Two things break without it, and neither says so:
#   * the ingest indexes the documents but does NOT stamp them, leaving whatever groups they had;
#   * `acl_group_map` is empty, so retrieval never sends the ACL header at all.
# The visible symptom is identical to the missing group claim — the agent says it found no
# authorized documents — which is exactly why both are set here, together, by the same script.
#
# Reuses an existing group by display name (idempotent) and adds the signed-in user, because a
# stamped index that nobody belongs to is fail-closed for everyone, including whoever just ran
# this. Non-fatal: without permission to create groups, the script says so and moves on.
GROUP_NAME="${APP_USERS_GROUP_NAME:-foundry-assured-app-users}"
echo "▸ Audience group ($GROUP_NAME)…"
GROUP_ID="$(az ad group list --display-name "$GROUP_NAME" --query "[0].id" -o tsv 2>/dev/null || true)"
if [ -z "${GROUP_ID:-}" ]; then
  GROUP_ID="$(az ad group create --display-name "$GROUP_NAME" --mail-nickname "$GROUP_NAME" \
    --query id -o tsv 2>/dev/null || true)"
  [ -n "${GROUP_ID:-}" ] && echo "  ✔ group created"
else
  echo "  · group already exists (reused)"
fi
if [ -n "${GROUP_ID:-}" ]; then
  ME="$(az ad signed-in-user show --query id -o tsv 2>/dev/null || true)"
  if [ -n "${ME:-}" ]; then
    if az ad group member check --group "$GROUP_ID" --member-id "$ME" --query value -o tsv 2>/dev/null | grep -qi true; then
      echo "  · you are already a member"
    else
      az ad group member add --group "$GROUP_ID" --member-id "$ME" 2>/dev/null \
        && echo "  ✔ added you to the group (an index nobody belongs to is closed to everyone)"
    fi
  fi
else
  echo "  ⚠ could not create/find the group — set APP_USERS_GROUP_ID by hand, or the selfwiki ACL"
  echo "    will index without stamping and retrieval will return nothing."
fi

# ---- Write env -------------------------------------------------------------
echo "▸ Writing env files…"
[ -n "${GROUP_ID:-}" ] && upsert "$BACK_ENV" APP_USERS_GROUP_ID "$GROUP_ID"
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
