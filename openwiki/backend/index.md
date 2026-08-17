# Files

- [Backend Overview](backend-overview.md) - Composition root and module map for the FastAPI backend, including boot order, domain mounting, declarative agent-definition seams, and shared-kernel boundaries.
- [Backend Evaluation and Tests](evaluation-and-tests.md) - Offline assurance gates, architecture tests, and backend-focused validation suites that define what the repository considers faithful, secure, and complete behavior.
- [Grounded Domains](grounded-domains.md) - Grounded question-answering domains such as selfwiki and techdocs, including the shared archetype, per-domain configuration, retrieval path, and declarative instruction ownership.
- [Helpdesk Workflow Domain](helpdesk-workflow.md) - The helpdesk runtime: per-request triage, retrieval, resolution, escalation, memory, OBO identity, and the hosted twin that drops live-step and HITL behavior.
- [Knowledge Pipeline](knowledge-pipeline.md) - Source-grounded wiki and docbundle generation, adaptation, ingest, ACL stamping, and fidelity gating that feed the repository’s grounded knowledge domains.
- [Oncall LangGraph Domain](oncall-graph.md) - LangGraph-based on-call triage runtime, including its edit-capable human approval flow, checkpointer requirements, mount gating, and coupling to the frontend graph approval UI.
- [Platform Ops Domain](platform-ops.md) - Tool-driven platform concierge over Microsoft MCP servers, including per-request tool assembly, role filtering, approval middleware, Foundry connection brokering, and hosted/live differences.
- [Backend State and Persistence](state-and-persistence.md) - State ownership map for backend runtime data: memory, tenant records, connections, tickets, hosted client caches, and interrupt/checkpointer durability constraints.
- [Tenancy and Admin](tenancy-and-admin.md) - Tenant resolution, control-plane persistence, onboarding and admin APIs, and the invariants that make shared mode safe without moving business domains into the shared kernel.
