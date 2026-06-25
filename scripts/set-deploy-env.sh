#!/usr/bin/env bash
# Copy the Entra values from the local .env files into the azd environment, so
# `azd up` can bake the browser-side NEXT_PUBLIC_* into the frontend image and wire
# the backend OBO secret. Reads from apps/backend/.env + apps/frontend/.env.local —
# nothing is hardcoded. Usage:  ./scripts/set-deploy-env.sh [azd-env-name]
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACK="$ROOT/apps/backend/.env"
FRONT="$ROOT/apps/frontend/.env.local"
ENVFLAG=()
[ "${1:-}" ] && ENVFLAG=(-e "$1")

val() { grep -E "^$1=" "$2" 2>/dev/null | head -1 | cut -d= -f2-; }

set_from() { # KEY FILE
  local v
  v="$(val "$1" "$2")"
  if [ -n "$v" ]; then
    azd env set "$1" "$v" "${ENVFLAG[@]}" >/dev/null && echo "  ✔ $1"
  else
    echo "  · skip $1 (empty in ${2##*/})"
  fi
}

echo "Setting azd env from .env files …"
set_from NEXT_PUBLIC_ENTRA_TENANT_ID     "$FRONT"
set_from NEXT_PUBLIC_ENTRA_SPA_CLIENT_ID "$FRONT"
set_from NEXT_PUBLIC_ENTRA_API_CLIENT_ID "$FRONT"
set_from ENTRA_TENANT_ID                 "$BACK"
set_from ENTRA_API_CLIENT_ID             "$BACK"
set_from ENTRA_API_CLIENT_SECRET         "$BACK"
echo "Done — now run:  azd up   (or: azd provision && azd deploy backend && azd deploy web)"
