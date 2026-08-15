# Files

- [Admin and operational APIs](admin-and-operations.md) - Backend HTTP APIs for admin management, user-role operations, tickets, evals, health, and caller identity, including their owning services and operational side effects.
- [Auth and tenancy seam](auth-and-tenancy.md) - Entra authentication, OBO credential flow, request-scoped user context, and the deployment-mode seam that keeps most backend code tenant-agnostic.
- [Grounded domains](grounded-domains.md) - Cockpit and selfwiki share a grounded Q&A archetype built from a single retrieval seam, structured citations, and tenant-aware access-control trimming.
- [Knowledge and assurance pipeline](knowledge-and-assurance.md) - Backend-owned corpus ingest, docbundle and OpenWiki adaptation, ACL stamping, wiki fidelity gates, and the test suites that keep knowledge artifacts trustworthy.
- [Backend overview](overview.md) - Composition root and runtime map for the FastAPI backend, including app startup, router aggregation, domain mounting, service boundaries, and the main invariants that constrain safe changes.
- [Platform domain](platform-domain.md) - The platform domain is the backend’s tool-driven concierge, distinct from grounded domains because it depends on tool availability, approval on writes, and a live-versus-hosted split that is still partly infra-gated.
- [Platform per-request agent proxy](platform-per-request-agent.md) - How the platform domain uses PerRequestAgent to satisfy AG-UI serving requirements while rebuilding caller-specific tools, tenant config, and OBO credentials on each request.
- [Platform tools and RBAC](platform-tools-and-rbac.md) - MCP server registry, tenant connection overlays, internal versus hosted tool construction, and the fail-closed authorization model behind the platform domain.
- [Tenant control plane](tenant-control-plane.md) - Shared-mode tenant records, onboarding, persistent store implementations, domain entitlements, and per-tenant connection/config ownership boundaries.
- [Helpdesk workflow domain](workflow-helpdesk.md) - The live helpdesk domain is the backend’s multi-agent workflow over AG-UI, combining triage, retrieval, resolution, per-user memory, and human-approved ticket escalation.
