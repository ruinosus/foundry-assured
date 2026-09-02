#!/usr/bin/env bash
set -euo pipefail

EXPECTED_SCOPE_ID="${1:?AZURE_DEVOPS_EXPECTED_SCOPE_REQUIRED}"
REGISTERED_SCOPE_IDS="${2:-}"

while IFS= read -r scope_id; do
  [ -z "$scope_id" ] && continue
  if [ "$scope_id" != "$EXPECTED_SCOPE_ID" ]; then
    echo "AZURE_DEVOPS_PERMISSION_EXCESSIVE" >&2
    exit 1
  fi
done <<< "$REGISTERED_SCOPE_IDS"