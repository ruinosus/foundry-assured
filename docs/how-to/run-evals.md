---
title: Run the evals
description: The offline policy gate, the cloud LLM-judge scores, the safety run, and the planted-violation self-test.
type: how-to
audience: operator
status: stable
updated: 2026-07-11
---

# Run the evals

Evaluation is a **hard gate**, not a report. The offline harness lives in `apps/backend/eval/`;
a policy violation exits non-zero and fails CI. Run everything from `apps/backend/`.

## The offline policy gate

```bash
cd apps/backend
uv run python -m eval.run_eval              # policy gate over real agent outputs
uv run python -m eval.run_eval --self-test  # prove the gate catches a PLANTED violation (offline)
```

The **LocalEvaluator** policies — *every answer cites a runbook or declines; never leak a
secret* — are the CI gate. `--self-test` plants a violation and asserts the gate catches it;
this is what `.github/workflows/ci.yml` runs on every PR (the `CI passed` check).

## Cloud LLM-judge scores

```bash
uv run python -m eval.run_eval --cloud      # + Foundry groundedness / relevance / coherence
```

`FoundryEvals` adds cloud LLM-judge scores viewable per-run in the Foundry portal (the run URL
carries the `eval_id`). Recorded runs surface on the frontend at `/evals`.

## Safety / adversarial run

```bash
uv run python -m eval.run_eval --safety [--cloud]
```

A refuse-or-ground gate over jailbreak prompts plus Foundry safety judges. Many jailbreaks are
stopped by Azure's content + jailbreak filter *before* the model (🛡️).

## The prompt-invariant suite (DNA)

Prompt contracts are guarded by a declarative eval suite over the runtime `.dna` scope — the
guard of record since prompts evolved into composed Soul + Guardrails
([ADR-013](../adr/ADR-013-declarative-agent-prompts-dna.md)):

```bash
dna eval run helpdesk-prompts --scope helpdesk   # offline, deterministic; exits 1 on any failed case
```

CI runs this via `uvx --from "dna-cli" dna eval run` against `apps/backend/.dna`.

## Continuous (online) evaluation

```bash
uv run python -m cli.provision_guardrail                    # runtime Content Safety RAI guardrail
uv run python -m cli.provision_eval_rule --eval-id eval_xxx # score every live RESPONSE_COMPLETED
```

The eval rule scores the agent's *live* responses and links each score to its trace in the
Foundry Control Plane. Full as-built model + thresholds: [the assurance mechanism](../METHOD.md)
(`apps/backend/eval/assurance.yaml`).
