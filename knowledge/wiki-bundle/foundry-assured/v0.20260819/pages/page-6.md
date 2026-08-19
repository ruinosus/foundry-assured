# Backend evaluation and tests

The backend ships its assurance claims as tests and thresholds, not just prose. `eval/assurance.yaml` names the repository’s core guarantees: groundedness, relevance, answer completeness, retrieval recall, citation floor, wiki fidelity, access-control violations, and red-team attack success rate. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/eval/assurance.yaml#L1-L13) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/eval/assurance.yaml#L16-L31)

## Evaluation surfaces

Two layers exist:

- **Offline eval harness** under `apps/backend/eval/`, including fidelity, prompt, contract, attribution, red-team, and access-control tests.
- **Application API surface** under `app/modules/evaluation/api.py`, which exposes recorded runs and live Foundry evaluation summaries to the frontend. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/eval/wiki_fidelity_test.py#L1-L19) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/eval/access_control_test.py#L1-L1) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/eval/red_team_test.py#L1-L1) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/evaluation/api.py#L19-L26) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/app/modules/evaluation/api.py#L39-L45)

## Architecture and route guards

The repo treats architectural boundaries as testable artifacts. `tests/architecture/module_graph_test.py`, `module_invocations_test.py`, and filesystem anchor tests guard dependency shape, while `tests/smoke/routes_snapshot_test.py` compares the mounted route surface against a committed snapshot. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/architecture/module_graph_test.py#L1-L1) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/architecture/module_invocations_test.py#L1-L1) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/smoke/routes_snapshot_test.py#L1-L1)

These are the fastest canaries after composition-root or router changes.

## Domain-specific high-signal tests

A few focused tests own especially important invariants:

- `tests/hitl/edit_roundtrip_test.py` — proves LangGraph `edit` decisions modify executed tool args, the reason oncall uses LangGraph. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/hitl/edit_roundtrip_test.py#L1-L19) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/hitl/edit_roundtrip_test.py#L102-L123)
- `tests/knowledge/retrieval_acl_parity_test.py` — proves per-user ACL trimming survives production retrieval code. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/knowledge/retrieval_acl_parity_test.py#L1-L18) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/knowledge/retrieval_acl_parity_test.py#L133-L142)
- `tests/platform_ops/mcp_brokering_e2e_test.py` — proves Foundry connection brokering and OBO token minting against live infrastructure. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/platform_ops/mcp_brokering_e2e_test.py#L1-L20) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/platform_ops/mcp_brokering_e2e_test.py#L154-L187)
- `tests/tenancy/tenant_e2e_test.py` — proves cross-tenant isolation and memory scoping. [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/tenant_e2e_test.py#L7-L19) [Source](https://github.com/ruinosus/foundry-assured/blob/b0a07a129bc3557f4a4d324dc1b7d050cf7bc1ad/apps/backend/tests/tenancy/tenant_e2e_test.py#L236-L260)

## Operational guidance

Use the smallest suite that owns the invariant you changed. Full eval sweeps are useful late; route snapshots, architecture tests, knowledge tests, or domain-specific E2Es are better first checks.
