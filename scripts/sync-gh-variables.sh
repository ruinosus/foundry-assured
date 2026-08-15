#!/usr/bin/env bash
# Sync the GitHub Actions *variables* from the azd environment — the direction that was missing.
#
# `set-deploy-env.sh` pushes .env → azd env so `azd up` can bake the frontend image. Nothing
# pushed azd env → GitHub, so the repository variables were typed by hand and drifted: after the
# `foundry-helpdesk` → `foundry-assured` rebrand renamed the Azure resources, five variables kept
# pointing at resources that no longer exist, and `eval-cloud.yml` failed **every Monday for eight
# weeks** (2026-06-29 → 2026-08-15) on `Name or service not known` without anyone noticing.
#
# Source of truth = `azd env get-values`. This script only reports drift unless you pass --apply.
#
# Usage (from the repo root):
#   ./scripts/sync-gh-variables.sh                 # report drift, change nothing (default)
#   ./scripts/sync-gh-variables.sh --apply         # write the drifted variables to GitHub
#   ./scripts/sync-gh-variables.sh --check         # report drift and exit 1 if any (for CI)
#   ./scripts/sync-gh-variables.sh -e <azd-env>    # read a specific azd environment
set -euo pipefail

APPLY=0
CHECK=0
ENVFLAG=()
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --check) CHECK=1 ;;
    -e) shift; ENVFLAG=(-e "${1:?-e needs an azd env name}") ;;
    -h|--help) sed -n '2,17p' "$0" | sed 's/^# \{0,1\}//'; exit 0 ;;
    *) echo "✖ unknown flag: $1" >&2; exit 2 ;;
  esac
  shift
done

command -v azd >/dev/null || { echo "✖ azd not found."; exit 1; }
command -v gh  >/dev/null || { echo "✖ gh not found."; exit 1; }

# The variables the workflows actually read (derived from `grep -rho 'vars\.[A-Z_]*' .github/workflows`)
# MINUS the ones GitHub owns rather than Azure — see NEVER_SYNC below.
SYNCED=(
  AZURE_ENV_NAME
  AZURE_LOCATION
  AZURE_SUBSCRIPTION_ID
  AZURE_TENANT_ID
  FOUNDRY_PROJECT_ENDPOINT
  FOUNDRY_MODEL
  AZURE_SEARCH_ENDPOINT
  AZURE_SEARCH_KNOWLEDGE_BASE
  AZURE_SEARCH_LOCATION
  AZURE_STORAGE_ACCOUNT
  AZURE_STORAGE_CONTAINER
  AZURE_STORAGE_RESOURCE_ID
  APP_USERS_GROUP_ID
  ENTRA_TENANT_ID
  ENTRA_API_CLIENT_ID
  NEXT_PUBLIC_ENTRA_TENANT_ID
  NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID
  NEXT_PUBLIC_ENTRA_API_CLIENT_ID
)

# Deliberately NOT synced, even though the workflows read them:
#   AZURE_CLIENT_ID    — the OIDC *deploy identity* (the `foundry-assured-ci` app registration).
#                        It is a GitHub↔Entra federation detail; azd knows nothing about it, and
#                        overwriting it breaks every cloud workflow's login.
#   RELEASE_APP_ID     — the release-please GitHub App. Same reasoning.
#   COCKPIT_TEST_USER_* — test identities for the security gates, not infrastructure output.
NEVER_SYNC="AZURE_CLIENT_ID RELEASE_APP_ID COCKPIT_TEST_USER_A COCKPIT_TEST_USER_B"

# Secrets never travel through here. `gh variable` is PLAINTEXT and readable by anyone with repo
# access — a secret set as a variable is a disclosure, so refuse the whole run rather than leak one.
for k in "${SYNCED[@]}"; do
  case "$k" in
    *SECRET*|*PASSWORD*|*_KEY) echo "✖ refusing: $k looks like a secret; use \`gh secret set\`." >&2; exit 2 ;;
  esac
done

echo "▸ Reading azd environment…"
# `${ENVFLAG[@]+...}` — expanding an empty array under `set -u` is an error on bash 3.2, which is
# what macOS still ships. Measured here, not theoretical.
AZD_VALUES="$(azd env get-values ${ENVFLAG[@]+"${ENVFLAG[@]}"} 2>/dev/null)" || { echo "✖ could not read the azd env."; exit 1; }

# `|| true` is load-bearing: under `set -e`, a grep that matches nothing fails, and a failing
# command substitution inside an assignment aborts the script. Without it, the first variable
# missing on either side kills the run — which is exactly the case this tool exists to report.
azd_val() { printf '%s\n' "$AZD_VALUES" | { grep -E "^$1=" || true; } | head -1 | cut -d= -f2- | sed 's/^"//; s/"$//'; }

echo "▸ Reading GitHub repository variables…"
GH_VALUES="$(gh variable list --json name,value --jq '.[] | "\(.name)=\(.value)"')"
gh_val() { printf '%s\n' "$GH_VALUES" | { grep -E "^$1=" || true; } | head -1 | cut -d= -f2-; }

drift=0
for k in "${SYNCED[@]}"; do
  want="$(azd_val "$k")"
  have="$(gh_val "$k")"
  if [ -z "$want" ]; then
    echo "  · $k — absent from the azd env, skipping"
  elif [ "$want" = "$have" ]; then
    echo "  = $k"
  else
    drift=$((drift + 1))
    echo "  ≠ $k"
    echo "      GitHub: ${have:-<unset>}"
    echo "      azd   : $want"
    if [ "$APPLY" = 1 ]; then
      gh variable set "$k" --body "$want" >/dev/null && echo "      ✔ updated"
    fi
  fi
done

echo
if [ "$drift" = 0 ]; then
  echo "✅ No drift — every synced variable matches the azd environment."
  exit 0
fi

if [ "$APPLY" = 1 ]; then
  echo "✅ Applied $drift change(s)."
  exit 0
fi

echo "⚠️  $drift variable(s) drifted. Re-run with --apply to write them."
echo "    Not synced by design: $NEVER_SYNC"
[ "$CHECK" = 1 ] && exit 1
exit 0
