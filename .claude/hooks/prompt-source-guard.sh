#!/usr/bin/env bash
# REGRA 7 (CLAUDE.md) — prompt muda no documento AgentSchema, nunca no Python que o compõe.
#
# `app/modules/agentdefs/` CARREGA e COMPÕE os prompts; o texto deles mora em
# `apps/backend/agents/assured/*.yaml`. Editar o Python para mudar redação faz o prompt
# divergir do documento que o `provision_agents` publica no Foundry — e o portal passa a
# mostrar uma versão que ninguém escreveu.
#
# Pergunta em vez de negar: mudar a LÓGICA de composição (ordem persona → instructions →
# guardrails, tratamento de PowerFx, seleção de AGENTS_DIR) é trabalho legítimo neste
# arquivo. O hook não sabe distinguir intenção, então força a decisão consciente.
set -euo pipefail

payload=$(cat)
path=$(printf '%s' "$payload" | jq -r '.tool_input.file_path // ""')

case "$path" in
  */app/modules/agentdefs/*) ;;
  *) exit 0 ;;
esac

jq -n '{
  hookSpecificOutput: {
    hookEventName: "PreToolUse",
    permissionDecision: "ask",
    permissionDecisionReason: "REGRA 7: este arquivo compõe prompts, não os contém. Se a mudança é de TEXTO de prompt, ela pertence a apps/backend/agents/assured/*.yaml (+ o eval-case correspondente, no mesmo PR). Se é de LÓGICA de composição, siga."
  }
}'
