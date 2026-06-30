#!/usr/bin/env bash
# One-shot "bring up the infra" orchestrator — chains the standard provisioning path
# from docs/DEPLOYMENT.md with up-front preflight checks, so a fresh clone goes from
# zero to a locally-runnable, provisioned Foundry Assured in one command. Idempotent:
# each stage it calls is itself safe to re-run.
#
# What it does (in order):
#   preflight  — tools installed (azd/az/uv/node) + you're logged in (azd + az)
#   1) azd up              — provision all Azure infra (Bicep control plane)
#   2) setup-entra.sh +    — OPTIONAL (--with-auth): the 2 Entra app regs (sign-in + OBO)
#      setup-app-roles.sh    + the 4 app roles (Admin/Author/Approver/Reader) for HITL/admin
#   3) bootstrap.sh        — fill .env from azd, ingest the helpdesk KB, provision memory
#   then prints the remaining steps (run local · deploy hosted · platform/Toolbox · stamp).
#
# Usage (from the repo root):
#   ./scripts/up-all.sh                 # provision + bootstrap (no sign-in; single identity)
#   ./scripts/up-all.sh --with-auth     # also create the Entra apps + app roles (sign-in + HITL)
#   ./scripts/up-all.sh --provision-only # just `azd up` (skip bootstrap/auth)
#   ./scripts/up-all.sh -h              # help
#
# It does NOT deploy to the cloud or publish the marketplace stamp — those need
# interactive post-deploy RBAC / a Partner Center account. The footer lists them.
# Full reference: docs/DEPLOYMENT.md · SaaS stamp: docs/D-PACKAGING-RUNBOOK.md.
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

WITH_AUTH=0
PROVISION_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --with-auth)      WITH_AUTH=1 ;;
    --provision-only) PROVISION_ONLY=1 ;;
    -h|--help)
      sed -n '2,33p' "$0" | sed 's/^# \{0,1\}//'
      exit 0 ;;
    *) echo "✖ unknown flag: $arg (try -h)"; exit 1 ;;
  esac
done

step() { printf '\n\033[1;36m▸ %s\033[0m\n' "$*"; }
ok()   { printf '  \033[32m✓\033[0m %s\n' "$*"; }
die()  { printf '\033[31m✖ %s\033[0m\n' "$*" >&2; exit 1; }

# ── Preflight ────────────────────────────────────────────────────────────────
step "Preflight — tools & sign-in"

command -v azd  >/dev/null || die "azd not found — install Azure Developer CLI (https://aka.ms/azd ≥ 1.26)."
command -v az   >/dev/null || die "az not found — install the Azure CLI (https://aka.ms/azcli ≥ 2.80)."
command -v uv   >/dev/null || die "uv not found — install uv (https://docs.astral.sh/uv)."
command -v node >/dev/null || die "node not found — install Node 20+."
ok "azd $(azd version 2>/dev/null | head -1 | awk '{print $NF}')  ·  az $(az version --query '\"azure-cli\"' -o tsv 2>/dev/null)  ·  uv $(uv --version 2>/dev/null | awk '{print $2}')  ·  node $(node --version)"

# node major ≥ 20
NODE_MAJOR="$(node --version | sed 's/^v//' | cut -d. -f1)"
[ "$NODE_MAJOR" -ge 20 ] || die "Node $NODE_MAJOR detected — need Node 20+."

# sign-in state (don't auto-login; these are interactive)
azd auth token >/dev/null 2>&1 || die "Not signed in to azd — run:  azd auth login"
az account show  >/dev/null 2>&1 || die "Not signed in to az — run:  az login"
SUB="$(az account show --query name -o tsv 2>/dev/null || echo '?')"
ok "signed in (azd + az) · subscription: $SUB"

# ── Stage 1: provision ────────────────────────────────────────────────────────
step "1/3 — Provisioning Azure infra (azd up)"
echo "  This runs infra/ (Foundry + AI Search + Storage + ACR + Container Apps)."
echo "  azd will prompt for an environment name + region on first run."
azd up
ok "infra provisioned"

if [ "$PROVISION_ONLY" = "1" ]; then
  step "Done (provision-only)."
  echo "  Next: ./scripts/bootstrap.sh   (fill .env + ingest the KB + memory)"
  exit 0
fi

# ── Stage 2: auth (optional) ──────────────────────────────────────────────────
if [ "$WITH_AUTH" = "1" ]; then
  step "2/3 — Entra app registrations + app roles (--with-auth)"
  echo "  Needs rights to create app registrations AND grant admin consent."
  ./scripts/setup-entra.sh
  # setup-app-roles needs the API client id setup-entra just wrote into apps/backend/.env
  API_ID="$(sed -n 's/^ENTRA_API_CLIENT_ID=\(.*\)$/\1/p' apps/backend/.env 2>/dev/null | head -1)"
  if [ -n "${API_ID:-}" ]; then
    ENTRA_API_CLIENT_ID="$API_ID" ./scripts/setup-app-roles.sh
    ok "Entra apps + 4 app roles (Admin/Author/Approver/Reader) ready"
    echo "  ⚠ Now assign YOURSELF the Admin role: Entra → Enterprise applications → the API app"
    echo "     → Users and groups → Add → you → role Admin   (required for HITL approval + /admin/users)"
  else
    echo "  ⚠ Could not read ENTRA_API_CLIENT_ID from apps/backend/.env — run scripts/setup-app-roles.sh by hand."
  fi
else
  step "2/3 — Auth (skipped)"
  echo "  Running WITHOUT sign-in (single DefaultAzureCredential identity)."
  echo "  Re-run with --with-auth to add Entra sign-in + the HITL/admin roles."
fi

# ── Stage 3: bootstrap (env + KB + memory) ────────────────────────────────────
step "3/3 — Bootstrap (fill .env from azd · ingest helpdesk KB · provision memory)"
./scripts/bootstrap.sh
ok "data plane bootstrapped (helpdesk KB + memory)"

# ── Next steps ────────────────────────────────────────────────────────────────
step "Provisioned. Run it locally:"
cat <<'EOF'
  cd apps/backend  && uv run uvicorn app.main:app --port 8000 --reload
  cd apps/frontend && npm install && npm run dev      # → http://localhost:3000

  Other KBs (optional, data-plane — see docs/DEPLOYMENT.md › Step 4):
    • cockpit   — COCKPIT_DOCBUNDLES=/path uv run python -m app.knowledge.ingest_cockpit
    • selfwiki  — ingests docs/wiki (already regenerated) via the env-override ingest

  Deploy to the cloud (optional — docs/DEPLOYMENT.md › Steps 6–7):
    • hosted agent:  azd deploy helpdesk-concierge   (then the post-deploy RBAC, or you get 403)
    • backend + web: ./scripts/set-deploy-env.sh && azd up

  SaaS / D-packaging add-ons (docs/D-PACKAGING-RUNBOOK.md):
    • platform domain (real tools): configure per-tenant Connections + the Foundry Toolbox
      (OAuth passthrough, ADR-011), then  azd deploy platform-concierge  + set TOOLBOX_NAME
    • shared multi-tenant:  DEPLOYMENT_MODE=shared + the Table tenant store + multi-tenant Entra
    • dedicated stamp:  the Managed Application marketplace path (needs a Partner Center account)

  Cost: ≈ $79/mo per data plane while up (~93% is AI Search Basic, no scale-to-zero).
    Stop the meter:   azd down --purge
EOF
ok "up-all complete"
