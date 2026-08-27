#!/usr/bin/env bash
# Desenvolvimento SEM Azure e SEM custo.
#
# O backend já tem os seams: `InMemoryTrail` e `InMemoryConversationStore` entram sozinhos
# quando `AZURE_STORAGE_ACCOUNT` está vazio, e `auth_enabled` é falso sem as vars do Entra.
# A única coisa que ele exige no boot é `FOUNDRY_PROJECT_ENDPOINT` — o SDK levanta
# `ValueError: Azure AI project endpoint is required` antes de qualquer requisição. Um endpoint
# SINTÁTICO resolve: nada é chamado enquanto a tela não pedir inferência, e um host que não
# existe não cobra nada.
#
# O QUE FUNCIONA assim: auditoria, conversas, chamados — tudo que lê dos stores em memória.
# O QUE NÃO FUNCIONA: chat e retrieval, que precisam de modelo e índice de verdade. Para esses,
# o modo demo (`npm run demo`) replica um fixture gravado do AG-UI, também sem Azure.
set -euo pipefail
ROOT="$(cd "$(dirname "$0")/.." && pwd)"
LOG=/tmp/foundry-dev
mkdir -p "$LOG"

pkill -f "uvicorn app.main:app" 2>/dev/null || true
pkill -f "next dev" 2>/dev/null || true

echo "== backend :8000 (stores em memória, sem Azure) =="
( cd "$ROOT/apps/backend" && \
  AZURE_STORAGE_ACCOUNT= AZURE_SEARCH_ENDPOINT= AZURE_AI_OPENAI_ENDPOINT= \
  ENTRA_TENANT_ID= ENTRA_API_CLIENT_ID= APP_USERS_GROUP_ID= \
  FOUNDRY_PROJECT_ENDPOINT="https://local.invalid/api/projects/dev" \
  uv run --no-sync uvicorn app.main:app --port 8000 --reload > "$LOG/backend.log" 2>&1 & )

echo "== frontend :3000 =="
( cd "$ROOT/apps/frontend" && \
  BACKEND_URL="http://localhost:8000" \
  npm run dev > "$LOG/frontend.log" 2>&1 & )

echo "== esperando =="
for _ in $(seq 1 60); do
  BE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:8000/audit/report 2>/dev/null || echo 000)
  FE=$(curl -s -o /dev/null -w '%{http_code}' --max-time 3 http://localhost:3000 2>/dev/null || echo 000)
  [ "$BE" = "200" ] && [ "$FE" = "200" ] && break
  sleep 2
done
echo "  backend  /audit/report -> ${BE:-000}"
echo "  frontend /             -> ${FE:-000}"
echo
echo "  http://localhost:3000/audit"
echo "  logs: $LOG/backend.log · $LOG/frontend.log"
echo "  parar: pkill -f 'uvicorn app.main:app'; pkill -f 'next dev'"
