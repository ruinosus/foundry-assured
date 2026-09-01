#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

cd "$ROOT_DIR"
uv run --project apps/backend --no-sync python scripts/gates.py

cd "$ROOT_DIR/apps/frontend"
npm run lint
npm run typecheck
npm run check:i18n
npm run build
