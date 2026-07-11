#!/usr/bin/env bash
# Demo mode — run the UI with NO Azure and NO Python backend. aimock (CopilotKit)
# replays a recorded AG-UI fixture; the real Next.js frontend renders the full flow
# (triage→retrieve→resolve steps, grounded answer, HITL approval). Record the fixture
# first with scripts/demo-record.sh. See docs/DEPLOYMENT.md › Demo mode.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
FRONT="$ROOT/apps/frontend"
PORT_MOCK="${PORT_MOCK:-4010}"

command -v npx >/dev/null || { echo "✖ npx not found — install Node 20+."; exit 1; }
command -v python3 >/dev/null || { echo "✖ python3 not found."; exit 1; }
if ! find "$FRONT/demo/fixtures" -name '*.json' | grep -q .; then
  echo "✖ No demo fixture under apps/frontend/demo/fixtures/."
  echo "  Record one first:  ./scripts/demo-record.sh"
  exit 1
fi
[ -d "$FRONT/node_modules" ] || ( cd "$FRONT" && npm install )

# AG-UI replay needs `aimock --config` with an inline `agui.fixtures` array (the bare
# llmock CLI only mounts /agui in record mode). Merge every recorded fixture file
# (flat or under agui-recorded/) into one config.
CONFIG="$(mktemp -t aimock-agui.XXXXXX.json)"
trap 'rm -f "$CONFIG"' EXIT
python3 - "$FRONT/demo/fixtures" "$CONFIG" <<'PY'
import json, glob, os, sys
src, out = sys.argv[1], sys.argv[2]
fixtures = []
for f in sorted(glob.glob(os.path.join(src, "**", "*.json"), recursive=True)):
    data = json.load(open(f, encoding="utf-8"))
    fixtures += data.get("fixtures", [data])
json.dump({"agui": {"path": "/agui", "fixtures": fixtures}}, open(out, "w"))
print(f"  {len(fixtures)} AG-UI fixture(s)")
PY

echo "▸ aimock (AG-UI replay) on :$PORT_MOCK …"
( cd "$FRONT" && npx -p @copilotkit/aimock aimock --config "$CONFIG" -p "$PORT_MOCK" ) &
MOCK_PID=$!
trap 'kill "$MOCK_PID" 2>/dev/null || true; rm -f "$CONFIG"' EXIT
sleep 2

echo "▸ Frontend in demo mode → http://localhost:3000  (Ctrl-C to stop both)"
cd "$FRONT"
AGUI_URL="http://localhost:$PORT_MOCK/agui" \
HOSTED_AGUI_URL="http://localhost:$PORT_MOCK/agui" \
NEXT_PUBLIC_DEMO_MODE=1 \
npm run dev
