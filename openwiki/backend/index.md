# Files

- [Backend API surface](api-surface.md) - Complete apps/backend HTTP and live endpoint surface, including mounted domain endpoints, hosted twins, operational routes, and their auth and protocol differences.
- [Auth and tenancy](auth-and-tenancy.md) - How apps/backend authenticates callers, exchanges OBO credentials, resolves tenants, enforces roles and domain entitlements, and persists tenant records.
- [Evaluation and assurance](evaluation-and-assurance.md) - The backend assurance harness, its fidelity and freshness gates, and the representative tests that encode apps/backend runtime invariants.
- [Grounded domains](grounded-domains.md) - The shared grounded-domain archetype behind cockpit and selfwiki, including retrieval, ACL handling, synthesis, citations, and hosted-versus-live distinctions.
- [Helpdesk workflow](helpdesk-workflow.md) - The multi-agent helpdesk workflow, its per-request identity and memory model, HITL escalation, and the stream-ordering workaround required by the AG-UI adapter.
- [Knowledge pipeline and docbundle contract](knowledge-pipeline.md) - Backend-owned ingestion, wiki adaptation, schema validation, and bundle generation paths that feed the grounded domains.
- [Operations and runtime behavior](operations-and-runtime.md) - Global runtime settings, startup and shutdown lifecycle, hosted-client caching, operational endpoints, persistence locations, and known runtime caveats in apps/backend.
- [Backend overview](overview.md) - Runtime map of the apps/backend service, its domain registry, deployment modes, and the main subsystems that compose the backend.
- [Platform domain and MCP brokering](platform-domain.md) - The tool-driven platform domain, its MCP server registry, per-request tool construction, connection-based credential brokering, and hosted-path variants.
- [Prompt and agent-definition system](prompt-system.md) - Declarative AgentSchema prompt loading, repository-owned prompt composition, AGENTS_DIR override behavior, and the boot-time failure rules that protect backend agent instructions.
