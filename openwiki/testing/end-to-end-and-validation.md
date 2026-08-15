---
type: testing-page
title: End-to-end tests and validation recipes
description: Playwright E2E coverage and focused validation commands for backend, frontend, infrastructure, and assurance-related changes.
tags: [testing, e2e, validation]
---

# End-to-end tests and validation recipes

This page collects the repository's highest-value validation paths, especially those that cross system boundaries.

## Playwright E2E suite

<!-- openwiki: broken internal link [../../e2e] file "../../e2e" does not exist. Fix the href or restore the target, then delete this comment. -->
The browser E2E suite lives in [`e2e`](../../e2e). Its README describes it as driving the **deployed** cloud app through real Entra sign-in and capturing:

- screenshots
- video
- traces
- HTML reports

Main files:

- `smoke.spec.ts`
- `cockpit-acl.spec.ts`
- `trigger.spec.ts`
- `playwright.config.ts`

## E2E scope

The E2E README says the current and next-step scope includes:

- sign in,
- visit helpdesk, cockpit, selfwiki, and platform,
- verify at least one grounded helpdesk answer,
- future or expanded coverage for HITL approval, ACL A/B differences, evals, and shared-mode admin flow.

A particularly important browser-path test is `cockpit-acl.spec.ts`, which validates ACL parity end to end by proving user A sees the confidential cockpit citation while user B does not.

This makes the E2E suite especially useful for validating auth, deployment, and UX integration together.

## Running E2E

From `e2e/`:

```bash
npm install
npm run install:browser
npm test
npm run report
```

The E2E README also notes required runtime environment variables such as `E2E_BASE_URL`, `E2E_USER`, and `E2E_PASS`, and warns about scale-to-zero cold starts and MFA constraints.

## Focused validation by change area

### Backend auth and tenancy

From `apps/backend/`:

```bash
uv run pytest eval/tenant_resolution_test.py eval/tenant_provider_test.py eval/domain_gate_test.py eval/memory_scope_test.py
```

### Backend retrieval and grounded answers

```bash
uv run pytest eval/retrieval_acl_parity_test.py eval/access_control_test.py eval/native_snippet_test.py eval/dockey_decode_test.py eval/grounded_archetype_roundtrip_test.py
```

### Helpdesk workflow and approval

```bash
uv run pytest eval/approval_mode_test.py eval/prompt_contract_test.py
```

### Platform and connection behavior

```bash
uv run pytest eval/mcp_registry_test.py eval/mcp_connect_test.py eval/connection_tools_build_test.py eval/rbac_per_tool_test.py eval/platform_hosted_bridge_test.py
```

### Knowledge pipeline and generated wiki

```bash
uv run pytest eval/docbundle_contract_test.py eval/wiki_fidelity_test.py eval/wiki_freshness_test.py
```

### Frontend static confidence

From `apps/frontend/`:

```bash
npm run lint
npm run typecheck
npm run build
```

### Infrastructure compile check

From repo root:

```bash
bicep build infra/main.bicep --stdout > /dev/null
```

## Demo mode as a lightweight validation path

`npm run demo` in `apps/frontend/` is not an integration test, but it is a good sanity check for:

- generic console rendering,
- evidence panel behavior,
- replayed workflow-step UX,
- demo-friendly product walkthroughs.

See [Frontend demo mode](../frontend/demo-mode.md).

## Choosing the narrowest useful check

A practical routing rule:

| Change area | Narrowest useful check |
| --- | --- |
| Auth or shared mode | tenant and domain gate tests |
| Grounded retrieval | retrieval ACL, snippet, and shape tests |
| Prompt or persona changes | `prompt_contract_test.py` |
| Wiki ingestion or adaptation | docbundle contract and wiki fidelity tests |
| Frontend UI-only changes | lint, typecheck, build, then demo mode or local browser check |
| Deploy or infra changes | Bicep build plus relevant workflow review |
| End-user sign-in or deployed UX | Playwright E2E |

## Related pages

- [Evaluation harness](../assurance/evaluation-harness.md)
- [Security and fidelity gates](../assurance/security-and-fidelity-gates.md)
- [Frontend demo mode](../frontend/demo-mode.md)
- [Automation and release](../operations/automation-and-release.md)
