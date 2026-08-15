---
type: assurance-page
title: Evaluation harness
description: Offline and cloud evaluation system for the backend, including datasets, deterministic policies, Foundry judges, thresholds, and representative test families.
tags: [assurance, evals, backend, testing]
---

# Evaluation harness

<!-- openwiki: broken internal link [../../apps/backend/eval] file "../../apps/backend/eval" does not exist. Fix the href or restore the target, then delete this comment. -->
The evaluation harness lives in [`apps/backend/eval`](../../apps/backend/eval). It is the repository's executable assurance layer, not a passive test directory.

The canonical overview in source is [`apps/backend/eval/README.md`](../../apps/backend/eval/README.md), and the main runner is [`apps/backend/eval/run_eval.py`](../../apps/backend/eval/run_eval.py).

## Two-layer model

The eval README describes two layers:

| Layer | Implementation | Purpose | CI gate |
| --- | --- | --- | --- |
| Deterministic policies | `assertions.py`, local evaluator checks | Enforce hard requirements such as citation presence or no secret leakage | Yes |
| Rubric / hosted judges | Foundry evals via cloud judges | Score groundedness, relevance, coherence, and other graded qualities | Usually informational, depending on workflow |

This distinction is central to the assurance mechanism. Hard guarantees and soft quality judgments are not conflated.

## Key files

| File | Purpose |
| --- | --- |
| `run_eval.py` | Main runner for local, cloud, safety, and self-test modes |
| `assertions.py` | Deterministic policy checks |
| `assurance.yaml` | Threshold and gate configuration |
| `datasets/golden.jsonl` | Curated Q&A dataset |
| `rubrics/helpdesk_quality.md` | Cloud rubric |
| `access_control_test.py` | Security gate for no cross-group leaks |
| `red_team_test.py` | Injection and exfiltration resistance |
| `prompt_contract_test.py` | Prompt invariant suite over AgentSchema definitions |
| `wiki_fidelity_test.py` | Wiki citation fidelity gate |

## Runner modes

The eval README documents these main invocations:

```bash
uv run python -m eval.run_eval
uv run python -m eval.run_eval --cloud
uv run python -m eval.run_eval --safety
uv run python -m eval.run_eval --safety --cloud
uv run python -m eval.run_eval --self-test
```

Meaning:

- plain run: local deterministic gate over real outputs,
- `--cloud`: include Foundry-hosted judges and portal-linked runs,
- `--safety`: use adversarial dataset,
- `--self-test`: plant a violation and prove the gate catches it offline.

## Threshold source of truth

`assurance.yaml` is the single source of truth for measured thresholds across:

- groundedness
- completeness
- retrieval recall
- citation floor
- build fidelity
- access-control violations
- red-team success-rate ceiling

That makes the assurance mechanism tunable without rewriting every test.

## Why context matters for groundedness

The eval README explains an important nuance: Foundry groundedness judges need a `context` field, but the concierge's final response does not necessarily echo all retrieved passages. The runner therefore feeds the expected source runbook as `context` from the golden dataset.

This means:

- deterministic citation checks remain the hard grounding guarantee,
- cloud groundedness scores remain the graded complement.

## Prompt contracts as part of evaluation

The prompt-contract suite is part of the evaluation harness, not separate from it. The README explains that after the AgentSchema migration, semantic invariants replaced byte-equivalence as the source of truth.

That makes prompt contracts a first-class assurance gate alongside citation and security checks.

## Relationship to frontend and backend runtime

The harness feeds several visible or operational systems:

- backend `/eval/foundry` surfaces cloud run results to the UI,
- frontend `/evals` renders those run summaries,
- CI uses self-test and other deterministic checks on every change,
- release and wiki workflows depend on related fidelity and freshness gates.

## Representative test families

### Deterministic correctness

- `assertions.py`
- `approval_mode_test.py`
- `configured_mode_test.py`
- `shared_boot_smoke_test.py`

### Tenancy and entitlement

- `tenant_resolution_test.py`
- `tenant_provider_test.py`
- `domain_gate_test.py`
- `tier_domains_test.py`

### Retrieval and grounding

- `retrieval_shape_test.py`
- `grounded_archetype_roundtrip_test.py`
- `native_snippet_test.py`

### Hosted paths

- `hosted_build_test.py`
- `platform_hosted_bridge_test.py`
- `platform_hosted_e2e_test.py`

### Wiki and docbundle assurance

- `docbundle_contract_test.py`
- `wiki_fidelity_test.py`
- `wiki_freshness_test.py`

## Validation

From `apps/backend/`:

```bash
uv run python -m eval.run_eval --self-test
```

For broader cloud-backed validation:

```bash
uv run python -m eval.run_eval --cloud
```

## Related pages

- [Security and fidelity gates](security-and-fidelity-gates.md)
- [Backend evaluations and tickets](../backend/evaluations-and-tickets.md)
- [Automation and release](../operations/automation-and-release.md)
