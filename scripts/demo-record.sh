#!/usr/bin/env bash
# Record the demo fixture: aimock proxies the REAL backend and saves the AG-UI stream
# to apps/frontend/demo/fixtures/ — commit it so anyone can replay with `./scripts/demo.sh`
# (zero Azure). Run the backend in its no-auth mode (no ENTRA_* in apps/backend/.env →
# DefaultAzureCredential, real Foundry + KB), so the mock can proxy without tokens.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONT="$ROOT/apps/frontend"
UPSTREAM="${UPSTREAM:-http://localhost:8000/helpdesk}"
PORT_MOCK="${PORT_MOCK:-4010}"
mkdir -p "$FRONT/demo/fixtures"

cat <<EOF
▸ Recording AG-UI fixtures from $UPSTREAM  →  apps/frontend/demo/fixtures/

  In two OTHER terminals, with Azure provisioned + 'az login':
    1) real backend (no-auth):  cd apps/backend  && uv run uvicorn app.main:app --port 8000
    2) frontend (record):       cd apps/frontend && AGUI_URL=http://localhost:$PORT_MOCK/agui \\
                                   NEXT_PUBLIC_DEMO_MODE=1 npm run dev

  Then open http://localhost:3000 and drive the demo: ask a grounded question, and
  ask to open a ticket + APPROVE it (captures the HITL). Press Ctrl-C here to stop +
  flush the fixtures, then commit apps/frontend/demo/fixtures/.
EOF
cd "$FRONT"
npx -p @copilotkit/aimock llmock -p "$PORT_MOCK" -f demo/fixtures \
  --agui-record --agui-upstream "$UPSTREAM" --log-level info
