#!/usr/bin/env bash
# Run the backend LOCALLY in SHARED (multi-tenant) mode — so you can exercise the tenant
# management UI (Connections page: onboard tenant + data-plane config + connection lifecycle)
# and the admin UI that only light up when DEPLOYMENT_MODE=shared.
#
# Why this exists: the DEPLOYED app is self_hosted (single-tenant), so /tenant isn't mounted
# (404) and the Connections page can't onboard. Nothing is missing from the code — the whole
# multi-tenant surface (app/api/tenant.py, the DomainAssignment seam, AdminUsers/Connections)
# is present; it's just gated behind shared mode. This flips that gate ON, with an in-memory
# tenant store (ephemeral — resets on restart, zero infra, no Azure Table needed).
#
# Usage (from the repo root):
#   ./scripts/dev-shared.sh                     # uses the default allow-listed tenant below
#   ALLOWED_TID=<your-tenant-guid> ./scripts/dev-shared.sh
#
# Then, in two more terminals:
#   1) cd apps/frontend && npm run dev          # http://localhost:3000
#   2) sign in (an Admin — your owner account or a test user with the Admin app role)
#      → the nav shows "Admin" + "Connections" (isAdmin)
#      → open Connections → "Onboard this tenant" → point it at your Foundry data plane
#      → /admin/users + /tenant now work end-to-end
#
# NOTE: shared mode validates Entra tokens from the caller's tenant against the API app reg.
# Sign in with a member of the allow-listed tenant (the test users in TEST-CREDENTIALS.local.md
# belong to jeffersonbarnabegmail.onmicrosoft.com). Admin role needed to onboard (re-login if
# you self-assigned it recently so the token carries the `roles` claim).
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT/apps/backend"

# The tenant allowed to onboard (the onboarding_guard checks tid ∈ ONBOARDING_ALLOWED_TIDS).
# Default: the jeffersonbarnabegmail.onmicrosoft.com tenant (owns the test users).
ALLOWED_TID="${ALLOWED_TID:-c5b891f7-65c2-4417-a5af-22cab24dc1d5}"

echo "▸ Foundry Assured — LOCAL shared-mode backend"
echo "    DEPLOYMENT_MODE   = shared"
echo "    TENANT_STORE      = memory (ephemeral)"
echo "    ONBOARDING_ALLOWED_TIDS = $ALLOWED_TID"
echo "    (auth + Foundry data-plane config come from apps/backend/.env)"
echo

DEPLOYMENT_MODE=shared \
TENANT_STORE_BACKEND=memory \
ONBOARDING_ALLOWED_TIDS="$ALLOWED_TID" \
  uv run uvicorn app.main:app --port 8000 --reload
