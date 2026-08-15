# Files

- [Admin and tenant management APIs](admin-and-tenant-apis.md) - Backend APIs for Graph-backed user administration, tenant onboarding and configuration, connection records, and per-tenant domain entitlement.
- [Declarative agent definitions](agent-definitions.md) - AgentSchema-based prompt definition system for backend agents, including scope catalogs, personas, guardrails, prompt composition order, and contract tests.
- [Backend application overview](application-overview.md) - Composition-root map of the FastAPI backend, including package boundaries, mounted endpoints, service seams, and the major runtime subsystems.
- [Backend auth and tenancy](auth-and-tenancy.md) - Entra authentication, On-Behalf-Of credentials, app-role checks, tenant resolution, and deployment-mode-specific configuration flow in the backend.
- [Backend domains and endpoints](domains-and-endpoints.md) - Public backend surface map covering domain registry rows, live AG-UI mounts, hosted bridges, and REST routers.
- [Evaluations and tickets](evaluations-and-tickets.md) - Backend support for persisted tickets, local and Foundry-backed evaluation APIs, and the runtime surfaces that expose assurance results to users.
- [Grounded domains](grounded-domains.md) - Implementation of the backend grounded-domain path for selfwiki and cockpit, including synthesis-only answering, citation emission, and per-domain configuration.
- [Helpdesk workflow](helpdesk-workflow.md) - Runtime design of the live helpdesk workflow, including triage, retrieval, resolution, memory, escalation, and approval-gated ticket creation.
- [Knowledge pipeline](knowledge-pipeline.md) - Backend pipeline for corpus ingest, docbundle adaptation, ACL stamping, generated wiki ingestion, and schema validation for grounded knowledge bases.
- [Platform domain](platform-domain.md) - The tool-driven backend domain for engineering operations, including live per-request tool brokering, hosted bridging, and approval-aware constraints.
- [Retrieval and ACL enforcement](retrieval-and-acl.md) - The backend retrieval seam for grounded domains, covering native KB retrieve, direct Search fallback, ACL token handling, docKey decoding, and security invariants.
