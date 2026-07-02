# ADR-004 — Data plane: BYO per-tenant, the Foundry project as the isolation boundary

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [SaaS target architecture](../superpowers/specs/2026-06-29-saas-target-architecture-design.md)

## Context

The product thesis is "the data is the customer's; we only orchestrate." We must decide where
each tenant's AI compute and data live and how they are isolated from other tenants.

## Decision

Each tenant **brings their own data plane** (BYO): their own Foundry project, Azure AI Search /
knowledge base, and storage. We never host the customer's models, KB, or data.

The **Foundry project is the isolation boundary** — Microsoft scopes access control, files,
agents, and evaluations to the project, and the "Agent standard setup with bring-your-own
storage" keeps data in the customer's storage account. One project per tenant gives data and
performance isolation by construction.

## Consequences

- **+** Strongest data isolation (different subscriptions/tenants), and compliance stays the customer's.
- **+** Aligns with the "we never store customer data" boundary ([ADR-005](./ADR-005-never-store-secrets.md)).
- **−** Every tenant must have (or provision) their own Foundry project — onboarding friction for customers without Azure.
- **−** We can't centralize inference cost/perf; per-tenant capacity is the customer's concern.
- **Future option:** a "managed data plane" tier (we host Foundry for customers without Azure) is possible later but is explicitly out of scope now (BYO-first).

## Alternatives considered

- **Shared Foundry/OpenAI instance across tenants** — easiest, but least data/perf isolation; contradicts the BYO thesis; rejected.

## Source (Microsoft guidance)

- [Microsoft Foundry architecture](https://learn.microsoft.com/azure/ai-foundry/concepts/architecture)
- [Multitenancy and Azure OpenAI](https://learn.microsoft.com/azure/architecture/guide/multitenant/service/openai)
- [AI/ML approaches for multitenant solutions](https://learn.microsoft.com/azure/architecture/guide/multitenant/approaches/ai-machine-learning)
