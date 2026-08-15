---
type: test-strategy
title: Testing and evaluation overview
description: Repository-wide test and assurance strategy covering backend proof-oriented eval suites, generated wiki gates, hosted bridging checks, multitenancy, and browser E2E.
tags: [testing, evals, assurance, e2e]
---

The repository uses tests for two different purposes: conventional regression checking and explicit assurance proofs. Many backend modules under `apps/backend/eval/` are less like unit tests and more like executable statements of the guarantees described in the README and ADRs.[`README.md`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/README.md#L155-L168) [`apps/backend/eval/assurance.yaml`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/assurance.yaml#L1-L32)

## Major backend test families

### Wiki and docbundle gates

These tests prove generated knowledge artifacts are structurally valid and source-grounded:

- `docbundle_contract_test.py`
- `wiki_fidelity_test.py`
- `wiki_freshness_test.py`

[`apps/backend/eval/docbundle_contract_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/docbundle_contract_test.py#L1-L27) [`apps/backend/eval/wiki_fidelity_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/wiki_fidelity_test.py#L1-L20) [`apps/backend/eval/wiki_freshness_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/wiki_freshness_test.py#L1-L58)

### Access control and retrieval proofs

These suites verify that retrieval and trimming do not leak unauthorized content:

- `access_control_test.py`
- `retrieval_acl_parity_test.py`
- `cockpit_acl_stamp_test.py`

[`apps/backend/eval/access_control_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/access_control_test.py#L1-L15) [`apps/backend/eval/retrieval_acl_parity_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/retrieval_acl_parity_test.py#L1-L64) [`apps/backend/eval/cockpit_acl_stamp_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/cockpit_acl_stamp_test.py#L1-L61)

### Multitenancy and control-plane proofs

These prove shared-mode isolation and lifecycle correctness:

- `tenant_provider_test.py`
- `tenant_store_test.py`
- `tenant_resolution_test.py`
- `tenant_scope_test.py`
- `tenant_admin_e2e_test.py`
- `tenant_e2e_test.py`
- `domain_gate_test.py`
- `enabled_domains_roundtrip_test.py`

[`apps/backend/eval/tenant_provider_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/tenant_provider_test.py#L1-L7) [`apps/backend/eval/tenant_store_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/tenant_store_test.py#L1-L63) [`apps/backend/eval/tenant_admin_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/tenant_admin_e2e_test.py#L1-L24)

### MCP and per-tool authorization proofs

These cover the tool-brokering and connection model behind platform behavior:

- `mcp_brokering_e2e_test.py`
- `mcp_connect_test.py`
- `mcp_registry_test.py`
- `rbac_per_tool_test.py`
- `connection_ops_test.py`
- `connection_store_test.py`
- `connection_tools_build_test.py`

[`apps/backend/eval/mcp_brokering_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/mcp_brokering_e2e_test.py#L1-L62) [`apps/backend/eval/rbac_per_tool_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/rbac_per_tool_test.py#L1-L64) [`apps/backend/eval/connection_ops_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/connection_ops_test.py#L1-L59)

### Hosted bridging and packaging proofs

These validate the hosted-agent integration layer:

- `hosted_build_test.py`
- `platform_hosted_bridge_test.py`
- `hosted_platform_smoke_test.py`
- `platform_hosted_e2e_test.py`

[`apps/backend/eval/hosted_build_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/hosted_build_test.py#L1-L62) [`apps/backend/eval/platform_hosted_bridge_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/platform_hosted_bridge_test.py#L1-L18)

### Runtime answer-quality and red-team proofs

These connect assurance claims to measured output quality and security behavior:

- `run_eval.py`
- `red_team_test.py`
- `approval_mode_test.py`

[`apps/backend/eval/run_eval.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/run_eval.py#L1-L64) [`apps/backend/eval/red_team_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/red_team_test.py#L1-L61) [`apps/backend/eval/approval_mode_test.py`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/apps/backend/eval/approval_mode_test.py#L1-L56)

## Browser E2E

The `e2e/` suite covers the deployed cloud app, not just local rendering. It drives real UI flows through Entra sign-in, MFA, multiple domains, hosted toggles, and evidence rendering.[`e2e/playwright.config.ts`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/e2e/playwright.config.ts#L3-L13) [`e2e/smoke.spec.ts`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/e2e/smoke.spec.ts#L30-L70) [`e2e/smoke.spec.ts`](https://github.com/ruinosus/foundry-assured/blob/4b749e7bac56789f0b1097cd4a8212b5c5c65d05/e2e/smoke.spec.ts#L170-L209)

## Minimal validation menu

Pick the narrowest check for the change you made:

- wiki or generated docs: `cd apps/backend && uv run python -m eval.docbundle_contract_test`
- retrieval or ACL: `cd apps/backend && uv run python -m eval.access_control_test`
- shared-mode control plane: `cd apps/backend && uv run python -m eval.tenant_store_test`
- hosted bridge: `cd apps/backend && uv run python -m eval.platform_hosted_bridge_test`
- full deployed UI: `cd e2e && npm test`

This menu is the shortest route from change intent to repository-native evidence.