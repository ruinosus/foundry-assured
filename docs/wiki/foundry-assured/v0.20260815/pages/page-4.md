# Evaluation and assurance

The backend does not treat quality claims as informal. `eval/assurance.yaml` is the single threshold file for repository-wide guarantees: it defines quality floors such as groundedness, relevance, answer completeness, retrieval recall, and citation floor; a build-time `fidelity_min`; and security thresholds like zero access-control violations and a red-team attack-success ceiling ([`apps/backend/eval/assurance.yaml`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/assurance.yaml#L1-L32)).

The practical consequence is that the backend’s validation surface is organized around invariants, not just around code areas. This page groups the important test families by what they prove.

## 1. Wiki and bundle quality gates

### Fidelity gate

`wiki_fidelity_test.py` is the external-bundle fidelity gate. It exists because `wiki_builder` already gates its own output, but adapted or externally generated bundles need the same enforcement. The test reuses `wiki_builder._fidelity_report` and `_fidelity_floor()` and fails if citations do not resolve to real source files or if any citation points into a worktree. The docstring explicitly says this matters more once regeneration is automated, because otherwise a hallucinated page could enter the KB unattended ([`apps/backend/eval/wiki_fidelity_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/wiki_fidelity_test.py#L1-L20), [`apps/backend/eval/wiki_fidelity_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/wiki_fidelity_test.py#L59-L97)).

### Freshness gate

`wiki_freshness_test.py` compares `generatedAt` in committed bundles against the newest git commit touching the source area and fails stale bundles. Its comments also explain the repository’s shift from per-area bundles to one repository-wide bundle so freshness grading would match the actual generator model ([`apps/backend/eval/wiki_freshness_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/wiki_freshness_test.py#L1-L13), [`apps/backend/eval/wiki_freshness_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/wiki_freshness_test.py#L26-L49), [`apps/backend/eval/wiki_freshness_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/wiki_freshness_test.py#L71-L119)).

### Bundle contract gate

`docbundle_contract_test.py` verifies both directions of the shared bundle contract: fields the backend reads must exist in the schema, fields it writes must exist in the schema, committed bundles under `docs/wiki/` must validate, and `groups: []` must remain distinguishable from missing groups. This is the structural quality gate behind ingestion safety ([`apps/backend/eval/docbundle_contract_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/docbundle_contract_test.py#L1-L27), [`apps/backend/eval/docbundle_contract_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/docbundle_contract_test.py#L124-L218)).

## 2. Prompt contracts and loader safety

`prompt_contract_test.py` is the semantic prompt gate. It is not just checking text presence arbitrarily; its docstring enumerates the exact prompt contracts runtime code depends on: sentinel strings like `TICKET:` and `NO_MATCH`, grounded citation duties, the ungrounded variant forbidding those duties, platform write-approval discipline, and pt-BR grounding behavior ([`apps/backend/eval/prompt_contract_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/prompt_contract_test.py#L1-L30)).

Before running prompt cases, it guards the guard itself by proving:

- an unknown agent raises instead of composing a placeholder,
- a failing check really fails,
- PowerFx indirection is refused,
- unknown AgentSchema fields are refused rather than silently dropped.

That means a green prompt suite is only trusted if the loader’s failure modes are also behaving correctly ([`apps/backend/eval/prompt_contract_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/prompt_contract_test.py#L109-L142), [`apps/backend/eval/prompt_contract_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/prompt_contract_test.py#L145-L166)).

## 3. Domain registry and mount invariants

`domain_registry_test.py` is the canonical composition test for domain registration. It proves there are exactly four domains, that the `kind` map matches the frontend’s conceptual model, that grounded domains carry the required config, that invalid grounded specs fail fast, and that `mount_domains(fake_app)` dispatches the right routes and adapter branches ([`apps/backend/eval/domain_registry_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/domain_registry_test.py#L1-L8), [`apps/backend/eval/domain_registry_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/domain_registry_test.py#L38-L71), [`apps/backend/eval/domain_registry_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/domain_registry_test.py#L87-L140)).

Related registry and API validation includes `domains_api_test.py`, `enabled_domains_roundtrip_test.py`, and `shared_boot_smoke_test.py`, which prove that domain entitlement state round-trips and shared-mode boot still mounts the expected surface ([`apps/backend/eval/domains_api_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/domains_api_test.py#L1-L46), [`apps/backend/eval/enabled_domains_roundtrip_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/enabled_domains_roundtrip_test.py#L1-L45), [`apps/backend/eval/shared_boot_smoke_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/shared_boot_smoke_test.py#L1-L38)).

## 4. Retrieval correctness and ACL enforcement

This family proves that grounded answers are both source-backed and access-controlled.

### Native snippet and docKey correctness

`native_snippet_test.py` proves that native searchIndex KB retrieval returns non-empty snippets through `references[].sourceData`, and `dockey_decode_test.py` proves that `docKey` decoding yields the correct blob URL rather than a broken fallback. These tests exist because both behaviors were discovered empirically, not inferred safely from docs ([`apps/backend/eval/native_snippet_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/native_snippet_test.py#L1-L79), [`apps/backend/eval/dockey_decode_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/dockey_decode_test.py#L1-L76)).

### ACL parity and access-control failures

`retrieval_acl_parity_test.py` is the main production-seam ACL proof. It drives the real `retrieve()` code path for two users with different access and asserts that the confidential source appears only for the authorized user. Its docstring is explicit that this catches failures the raw endpoint test cannot, such as dropped headers or mangled docKey parsing ([`apps/backend/eval/retrieval_acl_parity_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/retrieval_acl_parity_test.py#L1-L30), [`apps/backend/eval/retrieval_acl_parity_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/retrieval_acl_parity_test.py#L104-L143)).

`access_control_test.py` and `red_team_test.py` then elevate this to explicit security gates: zero unauthorized retrievals and a bounded prompt-leak attack success rate ([`apps/backend/eval/access_control_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/access_control_test.py#L1-L80), [`apps/backend/eval/red_team_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/red_team_test.py#L1-L66)).

### ACL stamping contract

`cockpit_acl_stamp_test.py` and related retrieval-shape tests prove that indexing and ACL restamping produce the fields and query-time behavior the retrieval seam expects ([`apps/backend/eval/cockpit_acl_stamp_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/cockpit_acl_stamp_test.py#L1-L63), [`apps/backend/eval/retrieval_shape_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/retrieval_shape_test.py#L1-L55)).

## 5. Tenancy, onboarding, and entitlement

The shared-mode backend has a large test family because tenancy is a runtime safety boundary.

- `tenant_resolution_test.py`, `tenant_provider_test.py`, and `tenant_store_test.py` cover current-tenant resolution and store semantics ([`apps/backend/eval/tenant_resolution_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tenant_resolution_test.py#L1-L45), [`apps/backend/eval/tenant_provider_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tenant_provider_test.py#L1-L41), [`apps/backend/eval/tenant_store_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tenant_store_test.py#L1-L41)).
- `tenant_scope_test.py`, `domain_gate_test.py`, `tier_domains_test.py`, and `enabled_domains_roundtrip_test.py` cover per-tenant domain entitlement behavior ([`apps/backend/eval/tenant_scope_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tenant_scope_test.py#L1-L37), [`apps/backend/eval/domain_gate_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/domain_gate_test.py#L1-L52), [`apps/backend/eval/tier_domains_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tier_domains_test.py#L1-L44)).
- `onboarding_guard_test.py` proves rollout allow-list behavior ([`apps/backend/eval/onboarding_guard_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/onboarding_guard_test.py#L1-L44)).
- `tenant_admin_e2e_test.py` and `tenant_e2e_test.py` are infra-gated end-to-end tests using real credentials and seeded stores to prove shared-mode isolation, onboarding, and memory-prefix behavior ([`apps/backend/eval/tenant_admin_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tenant_admin_e2e_test.py#L1-L80), [`apps/backend/eval/tenant_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tenant_e2e_test.py#L1-L19), [`apps/backend/eval/tenant_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/tenant_e2e_test.py#L217-L260)).

## 6. MCP brokering and per-tool RBAC

The platform domain has its own assurance surface because wrong behavior here can expose write tools or broker credentials incorrectly.

- `mcp_registry_test.py` checks registry data, classification, and role-visible tool sets ([`apps/backend/eval/mcp_registry_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/mcp_registry_test.py#L1-L54)).
- `connection_tools_build_test.py`, `connection_store_test.py`, and `rbac_per_tool_test.py` validate connection-backed tool building and stricter-of-both role enforcement ([`apps/backend/eval/connection_tools_build_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/connection_tools_build_test.py#L1-L52), [`apps/backend/eval/connection_store_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/connection_store_test.py#L1-L44), [`apps/backend/eval/rbac_per_tool_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/rbac_per_tool_test.py#L1-L50)).
- `mcp_brokering_e2e_test.py` is the infra-gated proof for live Foundry connection brokering, approval wiring, and OBO token minting ([`apps/backend/eval/mcp_brokering_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/mcp_brokering_e2e_test.py#L1-L21), [`apps/backend/eval/mcp_brokering_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/mcp_brokering_e2e_test.py#L154-L259)).

## 7. Hosted bridge behavior

Hosted bridges have both unit-like and infra-backed checks:

- `platform_hosted_bridge_test.py` proves the platform hosted bridge emits a clean AG-UI envelope even when no endpoint is configured, instead of crashing or returning malformed SSE ([`apps/backend/eval/platform_hosted_bridge_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/platform_hosted_bridge_test.py#L1-L60)).
- `platform_hosted_e2e_test.py`, `platform_hosted_smoke_test.py`, and `hosted_build_test.py` cover hosted build and runtime assumptions in increasingly live environments ([`apps/backend/eval/platform_hosted_e2e_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/platform_hosted_e2e_test.py#L1-L70), [`apps/backend/eval/hosted_platform_smoke_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/hosted_platform_smoke_test.py#L1-L36), [`apps/backend/eval/hosted_build_test.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/hosted_build_test.py#L1-L48)).

## 8. Offline and cloud eval harness

`run_eval.py` is the umbrella evaluation harness, while `eval/README.md` explains its modes and datasets. `foundry_evals.py` is the runtime-side reader for the canonical Foundry evaluation store. Together they form the backend’s broader measurement loop outside the narrow component tests listed above ([`apps/backend/eval/run_eval.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/eval/run_eval.py#L1-L80), `apps/backend/eval/README.md`, [`apps/backend/app/services/foundry_evals.py`](https://github.com/ruinosus/foundry-assured/blob/7e41ad6f80befa024fae867b3fcdf763f8331a10/apps/backend/app/services/foundry_evals.py#L1-L11)).

## Practical validation routing

- Prompt or agent-definition changes: `uv run python -m eval.prompt_contract_test`
- Domain registry or mounted-route changes: `uv run python -m eval.domain_registry_test`
- Retrieval or ACL changes: `uv run python -m eval.retrieval_acl_parity_test` plus `uv run python -m eval.native_snippet_test`
- Shared-mode auth or tenant changes: `uv run python -m eval.tenant_resolution_test` plus relevant tenant E2E tests
- MCP changes: `uv run python -m eval.mcp_registry_test` plus `uv run python -m eval.connection_tools_build_test`
- Hosted bridge changes: `uv run python -m eval.platform_hosted_bridge_test`
- Generated knowledge changes: `uv run python -m eval.docbundle_contract_test`, `uv run python -m eval.wiki_fidelity_test`, and `uv run python -m eval.wiki_freshness_test`
