#!/usr/bin/env bash
# One-shot "bring up the infra" orchestrator — chains the standard provisioning path
# from docs/DEPLOYMENT.md with up-front preflight checks, so a fresh clone goes from
# zero to a locally-runnable, provisioned Foundry Assured in one command. Idempotent:
# each stage it calls is itself safe to re-run.
#
# What it does (in order):
#   preflight  — tools installed (azd/az/uv/node) + you're logged in (azd + az)
#   1) OPTIONAL (--with-auth) — the 2 Entra app regs (sign-in + OBO) + the 4 app roles
#      (Admin/Author/Approver/Reader) + self-assign you the Admin role — BEFORE provision.
#   2) azd up   — provision + build + deploy. The azd HOOKS (azure.yaml) then auto-do:
#      • postprovision: push NEXT_PUBLIC_*/ENTRA_* into the azd env (so the web image builds with auth)
#      • postdeploy:    grant each hosted agent's instance identity its RBAC (the 403 fix) + register
#                       the deployed web URL as a SPA redirect URI (cloud sign-in)
#   3) bootstrap — ingest the helpdesk KB + provision memory (explicit + visible, not a silent hook).
#   No manual post-deploy commands. Genuinely-external bits (consent / Partner Center / Toolbox) remain.
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

# ── Stage 1: auth (optional, BEFORE provision) ────────────────────────────────
# App registrations need no infra; and the web image bakes NEXT_PUBLIC_* at BUILD time, so the
# Entra values must exist before azd's deploy phase. Doing auth first (then the postprovision hook
# pushes the values into the azd env) is what makes the deployed web sign-in actually work.
if [ "$WITH_AUTH" = "1" ]; then
  step "1/2 — Entra sign-in + app roles + Admin (--with-auth)"
  echo "  Needs rights to create app registrations + grant admin consent."
  ./scripts/setup-entra.sh
  API_ID="$(sed -n 's/^ENTRA_API_CLIENT_ID=\(.*\)$/\1/p' apps/backend/.env 2>/dev/null | head -1)"
  if [ -n "${API_ID:-}" ]; then
    ENTRA_API_CLIENT_ID="$API_ID" ./scripts/setup-app-roles.sh
    ENTRA_API_CLIENT_ID="$API_ID" ./scripts/assign-admin-role.sh || true   # you → Admin, via Graph (no portal click)
    ok "Entra apps + 4 app roles + Admin self-assigned"
  else
    echo "  ⚠ Could not read ENTRA_API_CLIENT_ID — run setup-app-roles.sh + assign-admin-role.sh by hand."
  fi
else
  step "1/2 — Auth skipped"
  echo "  Single DefaultAzureCredential identity (no sign-in). Re-run with --with-auth for Entra + HITL roles."
fi

# ── Stage 2: provision + deploy (azd up) — the hooks do env-push + agent RBAC + SPA redirect ──
# postprovision hook: push NEXT_PUBLIC_*/ENTRA_* into the azd env so the web image builds with auth.
# postdeploy hook:    grant each hosted agent's instance identity its RBAC (403 fix) + register the
#                     deployed web URL as a SPA redirect URI (cloud sign-in).
if [ "$PROVISION_ONLY" = "1" ]; then
  step "2/3 — azd provision (+ postprovision hook: env push)"
  azd provision
  ok "infra provisioned"
  echo "  Next: ./scripts/bootstrap.sh   (ingest the KB + memory)"
  exit 0
fi
step "2/3 — azd up (provision · build · deploy — hooks: env push · agent RBAC · SPA redirect)"
echo "  azd prompts for an environment name + region on first run."
azd up
ok "provisioned + deployed"

# ── Stage 3: bootstrap the data plane (EXPLICIT + visible — not a silent hook) ─────────────────
# The KB ingest is slow (polls for minutes) and data-plane-fragile, so it runs here in the open
# where you see progress/errors — not swallowed by a continueOnError azd hook.
step "3/3 — Bootstrap the data plane (ingest the helpdesk KB + provision memory)"
./scripts/bootstrap.sh
ok "KB ingested + memory provisioned"

# ── Done ──────────────────────────────────────────────────────────────────────
step "Done. The azd hooks automated the post-deploy steps:"
cat <<'EOF'
    ✓ NEXT_PUBLIC_*/ENTRA_* pushed into the azd env before the web build (sign-in works)
    ✓ each hosted agent's runtime RBAC granted          (postdeploy hook — the 403 fix)
    ✓ the deployed web URL registered as a SPA redirect (postdeploy hook — cloud sign-in)
    ✓ (--with-auth) you assigned the Admin app role     (Graph, no portal click)
  ✓ helpdesk KB ingested (Stage 3 above)

  Run it locally:
    cd apps/backend  && uv run uvicorn app.main:app --port 8000 --reload
    cd apps/frontend && npm install && npm run dev      # → http://localhost:3000

  Still manual (genuinely external):
    • Entra admin consent — only if your account lacked consent rights when setup-entra ran (1 portal click)
    • cockpit / selfwiki KBs — the per-domain ingest (cockpit needs a docbundles path); see DEPLOYMENT.md › Step 4
    • platform domain tools — bind a Foundry Toolbox + `azd env set TOOLBOX_NAME …` (ADR-011 / D-PACKAGING-RUNBOOK)
    • dedicated stamp — the Managed Application marketplace publish (Partner Center)

  Cost: ≈ $79/mo per data plane while up (~93% AI Search Basic).  Stop it:  azd down --purge
EOF
ok "up-all complete"
