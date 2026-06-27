# Eval & assurance harness

Offline evaluation **and the assurance gates** for the Helpdesk Concierge, built on the
**agent-framework native evaluation API** (`LocalEvaluator`, `@evaluator`, `FoundryEvals`,
`EvalItem`, `EvalResults`) — nothing hand-rolled. Two layers:

| Layer | What | Gates CI? |
| --- | --- | --- |
| **Policies** (`assertions.py`) | Deterministic `LocalEvaluator` checks: every answer must cite a runbook source (or decline) and must never leak a secret. | **Yes** — a violation exits non-zero. |
| **Rubric** (`rubrics/helpdesk_quality.md`) | Foundry hosted LLM-judges via `FoundryEvals`: groundedness / relevance / coherence. Scores land in the Foundry portal. | No — graded signal. |

## Layout

```
eval/
  datasets/golden.jsonl     # curated Q&A; each row names the runbook it should ground in
  assertions.py             # the executable ASSERT policies (LocalEvaluator checks)
  rubrics/helpdesk_quality.md  # the cloud rubric (Foundry quality evaluators)
  run_eval.py               # runner: agent -> EvalItems (with source as context) -> evaluate -> gate
  assurance.yaml            # the measured thresholds every gate reads (single source of truth)
  access_control_test.py    # security gate: agentic retrieve + app-side trim, per identity → no cross-group leak (violations_max: 0)
  red_team_test.py          # security gate: injection/exfil corpus through the same trim → ASR ≤ redteam_asr_max
  test_attribution.py       # round-trip check: chunk→component attribution agrees across the trim's two derivations
```

All thresholds live in **`assurance.yaml`** (quality: groundedness / completeness /
retrieval-recall / citation-floor; build: fidelity; security: access-control violations =
0 + red-team ASR ceiling). Start lenient, ratchet up. The security gates run in CI via
`.github/workflows/security-gates.yml`.

## Run (from `backend/`)

```bash
uv run python -m eval.run_eval              # local policy gate over real agent outputs (needs Azure auth + KB up)
uv run python -m eval.run_eval --cloud      # + Foundry groundedness/relevance/coherence (prints a portal URL)
uv run python -m eval.run_eval --safety     # adversarial/jailbreak set; gate on refuse-or-ground + no-secret
uv run python -m eval.run_eval --safety --cloud   # + Foundry safety judges (violence/self-harm/sexual/hate)
uv run python -m eval.run_eval --self-test  # plant a violation, prove the gate catches it (offline, no Azure)
```

`--safety` runs `datasets/adversarial.jsonl` (jailbreak / harmful / off-policy
prompts). Many are stopped by Azure's content + jailbreak filter *before* the
model (shown as 🛡️ blocked); the rest must refuse or stay grounded. The gate
fails if the agent gets jailbroken into off-policy content or leaks a secret.

The `--self-test` is what CI runs (`.github/workflows/eval-gate.yml`) — it needs
no Azure credentials, so the gate is enforceable on every push. `--cloud` runs
from a credentialed environment and links each run to its Foundry portal report.

## Why groundedness needs `context`

Foundry's groundedness judge checks the answer against a **context** document
(`mapping["context"] = "{{item.context}}"`, verified in `agent_framework_foundry`).
The concierge uses agentic KB search, which doesn't surface the retrieved passages
in its final response — so the runner feeds each `EvalItem` the source runbook
named in the golden row as `context`. The deterministic `cites_a_source` policy is
the hard grounding guarantee; the cloud groundedness score is the graded one.
