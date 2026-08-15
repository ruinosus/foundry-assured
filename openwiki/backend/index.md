# Files

- [Backend API surface](api-surface.md) - Contract-oriented map of backend HTTP endpoints, including auth and role gates, tenant ownership and onboarding rules, hosted bridges, Graph-backed admin behavior, and API-focused validation.
- [Auth and tenancy](auth-and-tenancy.md) - Request identity, OBO credentialing, shared-mode tenant resolution, entitlement checks, tenant configuration providers, persistence, and memory namespace rules.
- [Evaluation and assurance](evaluation-and-assurance.md) - Assurance model and validation suites for the backend, covering fidelity and freshness gates, prompt contracts, registry and API invariants, retrieval ACL correctness, tenancy, MCP brokering, and hosted bridges.
- [Grounded domains](grounded-domains.md) - Shared grounded-answer path for the cockpit and selfwiki domains, including domain registry data, retrieval and synthesis flow, ACL behavior, and AG-UI source emission.
- [Helpdesk workflow](helpdesk-workflow.md) - Live AG-UI workflow for the helpdesk domain, covering per-request identity, triage-retrieve-resolve-escalate execution, memory, human approval, and stream-ordering constraints.
- [Hosted bridges](hosted-bridges.md) - Bridges between hosted Foundry agents and the frontend’s AG-UI transport, including Responses re-encoding, platform Invocations passthrough, client caching, shutdown cleanup, and hosted-domain naming.
- [Knowledge pipeline](knowledge-pipeline.md) - Backend-owned pipeline that generates, adapts, validates, ingests, and ACL-stamps wiki and docbundle content into searchable Foundry and Azure Search corpora.
- [Operations and runtime](operations-and-runtime.md) - Runtime lifecycle, configuration surfaces, startup and shutdown behavior, local execution paths, and subsystem-oriented validation commands for the backend.
- [Backend overview](overview.md) - Composition map for the backend application, including the FastAPI entrypoint, domain registry, deployment-mode seam, and the major runtime subsystems behind each mounted endpoint.
- [Platform domain](platform-domain.md) - Tool-driven platform concierge for MCP-backed operations, including per-request agent construction, server registry governance, tenant connections, and caller-role filtering.
- [Prompt system](prompt-system.md) - Declarative AgentSchema prompt loading for backend agents, including scope catalogs, personas, guardrails, vendor extensions, environment resolution rules, and prompt-contract validation.
