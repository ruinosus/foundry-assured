#!/usr/bin/env bash
# Post-provision bootstrap: turn `azd up` outputs into a running local app.
# Idempotent — safe to re-run. Does the data-plane work that Bicep deliberately
# doesn't (KB ingestion + memory store) and writes the local .env files from the
# azd environment, so you don't copy-paste values by hand.
#
# Usage (from the repo root, after `azd up`):
#   ./scripts/bootstrap.sh
#
# Auth (Entra sign-in/OBO) is a separate, optional step — run scripts/setup-entra.sh.
# Without it the app runs under a single DefaultAzureCredential identity (no sign-in).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
BACK="$ROOT/apps/backend"
BACK_ENV="$BACK/.env"
FRONT_ENV="$ROOT/apps/frontend/.env.local"

command -v azd >/dev/null || { echo "✖ azd not found — install Azure Developer CLI first."; exit 1; }
command -v uv  >/dev/null || { echo "✖ uv not found — install uv (https://docs.astral.sh/uv)."; exit 1; }

echo "▸ Reading azd environment…"
VALUES="$(azd env get-values 2>/dev/null)" || { echo "✖ No azd env. Run 'azd up' first."; exit 1; }

# Pull KEY from `azd env get-values` output (KEY="value" lines).
val() { echo "$VALUES" | sed -n "s/^$1=\"\\(.*\\)\"$/\\1/p" | head -1; }

# Upsert KEY=VALUE into an env file without clobbering other keys (e.g. ENTRA_* you
# may have set via setup-entra.sh). Creates the file if missing.
upsert() { # FILE KEY VALUE
  local file="$1" key="$2" value="$3"
  touch "$file"
  if grep -qE "^$key=" "$file"; then
    # portable in-place edit (macOS + Linux): rewrite via awk
    awk -v k="$key" -v v="$value" -F= 'BEGIN{OFS="="} $1==k{$0=k"="v} {print}' "$file" > "$file.tmp" && mv "$file.tmp" "$file"
  else
    echo "$key=$value" >> "$file"
  fi
}

echo "▸ Writing $BACK_ENV (infra values from azd; ENTRA_* preserved)…"
for k in FOUNDRY_PROJECT_ENDPOINT FOUNDRY_MODEL AZURE_AI_OPENAI_ENDPOINT \
         FOUNDRY_EMBEDDING_MODEL AZURE_SEARCH_ENDPOINT AZURE_SEARCH_KNOWLEDGE_BASE \
         AZURE_STORAGE_ACCOUNT AZURE_STORAGE_RESOURCE_ID AZURE_STORAGE_CONTAINER \
         ARTIFACT_BLOB_ACCOUNT_URL ARTIFACT_STORE_ACCOUNT_URL; do
  v="$(val "$k")"
  [ -n "$v" ] && upsert "$BACK_ENV" "$k" "$v" && echo "  ✔ $k"
done
upsert "$BACK_ENV" FOUNDRY_MEMORY_STORE "$(val FOUNDRY_MEMORY_STORE || echo helpdesk-memory)"
upsert "$BACK_ENV" FRONTEND_ORIGIN "http://localhost:3000"

echo "▸ Writing ${FRONT_ENV}…"
upsert "$FRONT_ENV" AGUI_URL "http://localhost:8000/helpdesk"

echo "▸ Ingesting the knowledge base (corpus → Foundry IQ KB; a few minutes)…"
( cd "$BACK" && uv run python -m app.knowledge.ingest )

echo "▸ Provisioning the Foundry memory store…"
( cd "$BACK" && uv run python -m cli.provision_memory )

cat <<EOF

✅ Bootstrap done. Next:

  • Run it:        cd apps/backend  && uv run uvicorn app.main:app --port 8000 --reload
                   cd apps/frontend && npm install && npm run dev   # http://localhost:3000
  • Sanity check:  cd apps/backend  && uv run python -m eval.run_eval

  • Want sign-in (Entra ID + OBO)?  ./scripts/setup-entra.sh
    (without it the app runs under one DefaultAzureCredential identity — no login wall.)
EOF
