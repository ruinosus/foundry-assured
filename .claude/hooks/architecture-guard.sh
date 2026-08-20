#!/usr/bin/env bash
# REGRAS 8 e 9 (CLAUDE.md), verificadas a cada edição de .py no backend:
#
#   regra 8 — fronteiras de módulo (import-linter, 22 contratos)
#   regra 9 — nenhum caminho contado por `parents[N]` a partir do próprio arquivo
#
# NÃO reimplementa nenhuma das duas, e NÃO nomeia os comandos: pede a `scripts/gates.py` os
# gates cujo nome casa com o filtro, e ele os deriva do `ci.yml`. Se o comando de um deles
# mudar no workflow, muda aqui junto. Um hook que carrega sua própria cópia do comando é a
# mesma falha que este conjunto de aceleradores existe para evitar.
#
# O CLAUDE.md manda rodar `lint-imports` "antes de commitar" e a regra 9 tem gate próprio —
# mas ambos dependiam de alguém lembrar. Custam ~1s juntos.
#
# PostToolUse, não PreToolUse: os dois gates leem a árvore do disco, então precisam do
# arquivo já escrito.
set -euo pipefail

payload=$(cat)
path=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // .tool_response.filePath // ""')

case "$path" in
  */apps/backend/*.py) ;;
  *) exit 0 ;;
esac

repo="${path%%/apps/backend/*}"
# Captura rc e saída separadamente: com `cmd | grep` o exit code viraria o do grep.
output=$(cd "$repo" && uv run --project apps/backend --no-sync python scripts/gates.py \
  -k 'anchors|import-linter' 2>&1) && rc=0 || rc=$?
output=$(printf '%s\n' "$output" | grep -v '^warning: `VIRTUAL_ENV' || true)

if [ "$rc" -ne 0 ]; then
  jq -n --arg out "$output" '{
    decision: "block",
    reason: ("Gate de arquitetura vermelho depois desta edição (CLAUDE.md regras 8 e 9). Corrija antes de seguir — import cross-module só via `public`; caminho ancorado em `app`, nunca contado por parents[N].\n\n" + $out)
  }'
fi
