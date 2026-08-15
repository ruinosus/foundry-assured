# Files

- [Admin, tenant management, and tickets](admin-and-tickets.md) - Administrative HTTP surfaces for Graph-backed user management, tenant-scoped connection management, and persisted ticket records opened by the helpdesk workflow.
- [Declarative agent definitions and prompt assets](agentdefs.md) - How the backend loads AgentSchema prompt documents, composes personas and guardrails, selects baked versus mounted prompt directories, and publishes runtime prompt updates.
- [Grounded domains archetype](grounded-domains.md) - Shared serving archetype for cockpit and selfwiki, including request-scoped user capture, retrieval-to-synthesis flow, AG-UI event emission, and structured citation delivery.
- [Helpdesk workflow module](helpdesk.md) - The helpdesk domain’s workflow runtime, including per-request agent construction, memory wiring, escalation approval, and stream-order invariants.
- [Hosted bridges and evaluation APIs](hosted-bridges-and-evals.md) - Backend support for hosted-agent invocation, AG-UI bridging, lifecycle cleanup, and evaluation data endpoints, including verified versus infra-gated behavior.
- [Knowledge ingestion and ACL stamping](knowledge-ingestion.md) - Ingestion lifecycle for helpdesk and docbundle-based corpora, including blob upload, knowledge source and base creation, explicit indexer triggering, and ACL metadata stamping.
- [Knowledge retrieval and ACL enforcement](knowledge-retrieval.md) - Retrieval seam for grounded domains, including native and direct-search paths, per-user search tokens, docKey decoding, centralized dedupe, and fail-closed ACL behavior.
- [Backend overview](overview.md) - Composition-root map for the FastAPI backend, including lifecycle ordering, module boundaries, router inclusion, and domain mounting. Start here before changing any backend module.
- [Platform operations domain](platform-ops.md) - Tool-driven platform concierge over MCP servers, including registry-as-data, per-tool RBAC, connection-driven builds, and the split between internal and hosted tool acquisition.
- [Tenancy and deployment-mode seam](tenancy.md) - How the backend selects single-tenant versus shared behavior, resolves per-request tenant config, stores connection metadata, gates enabled domains, and scopes memory.
- [Wiki adaptation and docbundle contracts](wiki-and-docbundles.md) - How generated wiki outputs become ingestable docbundles, how OpenWiki and deep-wiki producers are adapted, and how the repository preserves freshness and fidelity contracts.
