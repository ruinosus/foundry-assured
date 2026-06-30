#!/usr/bin/env bash
# azd POSTPROVISION hook — runs after infra is created, BEFORE the package/build/deploy phase.
#
# Pushes the local .env (NEXT_PUBLIC_*/ENTRA_*) into the azd env — the web image bakes the sign-in
# config at BUILD time (Docker buildArgs), so it must be in the azd env BEFORE the deploy phase.
# Harmless/idempotent when auth isn't set up (nothing to push).
#
# NOTE: the KB ingest (scripts/bootstrap.sh) is deliberately NOT here — it's slow (polls for minutes)
# and data-plane-fragile, so it runs as an EXPLICIT, visible step in scripts/up-all.sh (after deploy)
# rather than swallowed by this continueOnError hook, where a failure would be silent.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"

echo "▸ postprovision: pushing local env into the azd environment (for the web build)"
if [ -x "$ROOT/scripts/set-deploy-env.sh" ]; then
  "$ROOT/scripts/set-deploy-env.sh" || echo "  (set-deploy-env: nothing to push)"
fi
