# Architecture Decision Records

ADRs capture significant architecture decisions: context → decision → consequences, each
grounded in the Microsoft guidance it follows. Format is lightweight (MADR-style).

## Index

| ADR | Decision |
|---|---|
| [ADR-001](./ADR-001-tenancy-deployment-stamps.md) | Tenancy model = **Deployment Stamps** (hybrid: shared + dedicated) |
| [ADR-002](./ADR-002-dedicated-stamp-managed-app-lighthouse.md) | Dedicated stamp = **Managed Application**; cross-tenant mgmt = **Azure Lighthouse** |
| [ADR-003](./ADR-003-multitenant-identity-obo.md) | Identity = **multi-tenant Entra app**, tenant from `tid`, **OBO** downstream |
| [ADR-004](./ADR-004-byo-data-plane-foundry-project.md) | Data plane = **BYO per-tenant**, Foundry **project** as the isolation boundary |
| [ADR-005](./ADR-005-never-store-secrets.md) | The control plane **never stores customer secrets** (passthrough + CMK refs) |
| [ADR-006](./ADR-006-tenant-scoped-config.md) | **Tenant-scoped** config — replace the global `settings`; namespace memory by tenant |
| [ADR-007](./ADR-007-coexistence-deployment-mode.md) | Coexistence via a **deployment-mode** seam (one codebase, three modes) |
| [ADR-008](./ADR-008-foundry-connections-app-configuration.md) | Use **Foundry connections + Azure App Configuration + Key Vault**, not a custom credential store |
| [ADR-009](./ADR-009-native-tool-approval-foundry-connection-resolution.md) | **Native tool-approval + Foundry-connection credential resolution** — no self-read Key Vault, no hand-rolled HITL |
| [ADR-010](./ADR-010-per-tenant-domain-entitlement.md) | Per-tenant domain enablement = **license entitlement** (stored on the tenant record), not a feature flag |
| [ADR-011](./ADR-011-hosted-per-tenant-foundry-toolbox-passthrough.md) | Hosted per-tenant tool resolution = **Foundry Toolbox + OAuth identity passthrough** (the agent never handles credentials) |
| [ADR-012](./ADR-012-reuse-upstream-deep-wiki-tooling.md) | Self-wiki generation = **reuse the upstream `microsoft/skills` deep-wiki plugin** (vendored at `.github/skills/`) + OpenWiki-style freshness regen; keep only our assurance layer |
| [ADR-013](./ADR-013-declarative-agent-prompts-dna.md) | Agent instructions = **declarative DNA scope** (`apps/backend/.dna/helpdesk/`, `dna-sdk` from PyPI); `prompts.py` becomes a composition shim guarded by a byte-equivalence gate + prompt-invariant eval suite in CI |
| [ADR-014](./ADR-014-runtime-prompt-scope-no-rebuild.md) | Runtime prompt scope **decouples from the image** — local: compose bind-mount over the baked copy; prod (ACA): Azure Files share at `/mnt/dna` selected via `DNA_BASE_DIR`, baked copy as fallback (`scripts/push-prompts.sh`); prompt edits = **restart, not rebuild**; Postgres source documented as the multi-replica evolution |

ADRs 001–007 belong to the [SaaS target architecture](../superpowers/specs/2026-06-29-saas-target-architecture-design.md) design; ADR-008 refines connection/secret storage for [sub-project B](../superpowers/specs/2026-06-29-subproject-b-connections-design.md); ADR-009 the credential brokering + write approval for [sub-project C](../superpowers/specs/2026-06-29-subproject-c-credential-brokering-design.md); ADR-010 the per-tenant domain entitlement for [sub-project D-runtime](../superpowers/specs/2026-06-29-subproject-d-runtime-design.md); ADR-011 the hosted Toolbox passthrough for [sub-project D-packaging](../superpowers/specs/2026-06-29-subproject-d-packaging-design.md).
