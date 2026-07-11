#!/usr/bin/env bash
# azd POSTDEPLOY hook — grant each hosted agent's deploy-time instance identity its runtime roles.
#
# Why a hook (and not Bicep): the Foundry platform mints a FRESH managed identity for each hosted
# agent AT DEPLOY time, so it can't be pre-assigned in Bicep. Without these roles the agent deploys
# fine but returns 403 at runtime. This reconciles them automatically after every `azd deploy`/`azd up`.
# Idempotent: `az role assignment create` is a no-op when the assignment already exists.
#
# Reads the account/search ARM ids from the azd env (bicep outputs AZURE_AI_ACCOUNT_ID / AZURE_SEARCH_ID),
# with a back-compat fallback for envs provisioned before those outputs existed.
set -euo pipefail

ROLE_AI_USER=53ca6127-db72-4b80-b1b0-d745d6d5456d        # Azure AI User — call the model
ROLE_SEARCH_READER=1407120a-92aa-4202-b7e9-c0e197c71c8f  # Search Index Data Reader — query the KB
AGENTS="helpdesk-concierge cockpit-expert selfwiki-expert platform-concierge"

VALUES="$(azd env get-values 2>/dev/null)" || { echo "  (no azd env — skipping agent RBAC)"; exit 0; }
val() { echo "$VALUES" | sed -n "s/^$1=\"\(.*\)\"\$/\1/p" | head -1; }

ACC_ID="$(val AZURE_AI_ACCOUNT_ID)"
# back-compat: derive the account id by stripping /projects/<name> off the project id
[ -z "$ACC_ID" ] && ACC_ID="$(val AZURE_AI_PROJECT_ID | sed 's#/projects/[^/]*$##')"
SRCH_ID="$(val AZURE_SEARCH_ID)"
# back-compat: resolve the search id from its endpoint name + the RG of the account
if [ -z "$SRCH_ID" ] && [ -n "$ACC_ID" ]; then
  SNAME="$(val AZURE_SEARCH_ENDPOINT | sed -E 's#https://([^.]+)\..*#\1#')"
  RG="$(echo "$ACC_ID" | sed -E 's#.*/resourceGroups/([^/]+)/.*#\1#')"
  [ -n "$SNAME" ] && [ -n "$RG" ] && SRCH_ID="$(az search service show -n "$SNAME" -g "$RG" --query id -o tsv 2>/dev/null || true)"
fi
[ -z "$ACC_ID" ] && { echo "  ⚠ no Foundry account id in the azd env — skipping agent RBAC"; exit 0; }

assign() { # principalId roleGuid scope label
  if az role assignment create --assignee-object-id "$1" --assignee-principal-type ServicePrincipal \
       --role "$2" --scope "$3" >/dev/null 2>&1; then
    echo "    ✓ $4"
  else
    echo "    · $4 (already assigned or insufficient rights)"
  fi
}

echo "▸ postdeploy: reconciling hosted-agent instance-identity RBAC"
for agent in $AGENTS; do
  AID="$(azd ai agent show "$agent" -o json 2>/dev/null | python3 -c '
import sys, json
try:
    d = json.load(sys.stdin)
    print((d.get("instance_identity") or {}).get("principal_id", ""))
except Exception:
    print("")' 2>/dev/null)"
  if [ -z "$AID" ]; then
    echo "  - $agent: not deployed / no instance identity yet (skip)"
    continue
  fi
  echo "  $agent ($AID):"
  assign "$AID" "$ROLE_AI_USER" "$ACC_ID" "Azure AI User → account"
  # grounded agents query the KB; platform is tool-driven (no search) — granting it is harmless.
  [ -n "$SRCH_ID" ] && assign "$AID" "$ROLE_SEARCH_READER" "$SRCH_ID" "Search Index Data Reader → search"
done
echo "  ✓ agent RBAC reconciled"

# ── Register the deployed web URL as a SPA redirect URI ───────────────────────────────────────
# The web FQDN is only known AFTER deploy, so the SPA app reg can't have it up front — without it
# cloud sign-in fails with AADSTS50011 (redirect URI mismatch). Merge it in idempotently.
WEB_URL="$(val WEB_URL | sed 's#/$##')"
SPA_APPID="$(val NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID)"
if [ -n "$WEB_URL" ] && [ -n "$SPA_APPID" ]; then
  SPA_OBJ="$(az ad app show --id "$SPA_APPID" --query id -o tsv 2>/dev/null || true)"
  if [ -n "$SPA_OBJ" ]; then
    CUR="$(az ad app show --id "$SPA_APPID" --query 'spa.redirectUris' -o json 2>/dev/null || echo '[]')"
    if echo "$CUR" | grep -qF "$WEB_URL"; then
      echo "  ✓ SPA redirect URI already includes the deployed web ($WEB_URL)"
    else
      NEW="$(python3 -c '
import json, sys
cur = json.loads(sys.argv[1] or "[]")
uris = sorted(set(cur + ["http://localhost:3000", sys.argv[2]]))
print(json.dumps(uris))' "$CUR" "$WEB_URL")"
      if az rest --method PATCH --url "https://graph.microsoft.com/v1.0/applications/$SPA_OBJ" \
           --headers "Content-Type=application/json" --body "{\"spa\":{\"redirectUris\":$NEW}}" >/dev/null 2>&1; then
        echo "  ✓ added the deployed web URL as a SPA redirect URI ($WEB_URL)"
      else
        echo "  · could not patch the SPA redirect URIs (insufficient rights?) — add $WEB_URL by hand"
      fi
    fi
  fi
fi
