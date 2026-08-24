---
name: prompt-change
description: Use ao criar ou editar qualquer documento AgentSchema em apps/backend/agents/assured/ (triage.yaml, resolve.yaml, techdocs.yaml, platform.yaml, personas/, guardrails/, scope.yaml) — ou quando pedirem para mudar o comportamento, a persona, o tom ou as regras de um agente. Garante que o eval-case correspondente mude no mesmo PR e que o Foundry seja republicado.
---

# Mudança de prompt declarativo

Prompt não se edita em Python (regra 7). A fonte é o documento AgentSchema. O que segue é o que
NÃO se enxerga só olhando o `.yaml`.

## 1. Antes de editar — descubra o que o prompt já promete

O eval-case correspondente em `agents/assured/eval-cases/` é a lista de invariantes que aquele
prompt sustenta, **cada uma com o motivo escrito ao lado**. Leia antes de mexer:

```bash
ls apps/backend/agents/assured/eval-cases/
```

Uma invariante lá não é preferência de estilo — é comportamento que alguém já perdeu uma vez.
Se sua edição remove uma frase que um `contains` procura, você não está limpando o prompt: está
removendo uma garantia.

## 2. Onde cada coisa mora

| O quê | Onde |
|---|---|
| Instrução do agente | `agents/assured/<agente>.yaml` (o delta daquele agente) |
| Persona compartilhada | `agents/assured/personas/*.md` |
| Regra cross-cutting | `agents/assured/guardrails/*.md` |
| Catálogo de escopo | `agents/assured/scope.yaml` |

Um agente referencia persona/guardrail **por nome**, em `metadata`, sob `x-foundry-assured`.
A composição é de ordem fixa: persona → instructions → additionalInstructions → guardrails.

**PowerFx (`=Env.X`) é recusado no load** — não é suportado, e o reader devolveria a string
literal. Não introduza.

## 3. Depois de editar — os três passos, nesta ordem

1. **Atualize o eval-case no mesmo PR.** Contrato de prompt que muda sem o caso correspondente
   é o que o gate pega:
   ```bash
   cd apps/backend && uv run python -m eval.prompt_contract_test
   ```
2. **Republique no Foundry.** SEGUNDA MÁXIMA — o agente existe lá, não aqui. Um prompt que
   mudou só no repo deixa o portal mostrando a versão anterior:
   ```bash
   cd apps/backend && uv run python -m cli.provision_agents
   ```
   Em ambiente com Azure Files montado, `./scripts/push-prompts.sh` publica sem redeploy.
3. **Rode os gates** — `/gates` (vários outros dependem de texto de prompt, não só o contract
   test).

## 4. Erros que já aconteceram

- Editar `app/modules/agentdefs/public.py` para mudar redação. Ele **compõe**, não contém — e um
  hook pergunta antes de deixar. Se o texto muda, ele muda no `.yaml`.
- Mudar o prompt e não o eval-case: o CI pega, mas só depois de você achar que terminou.
- Mudar o prompt e não republicar: o portal e o produto passam a discordar, em silêncio.
