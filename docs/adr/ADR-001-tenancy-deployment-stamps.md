# ADR-001 — Tenancy model: Deployment Stamps (hybrid)

- **Status:** Accepted
- **Date:** 2026-06-29
- **Context spec:** [SaaS target architecture](../superpowers/specs/2026-06-29-saas-target-architecture-design.md)

## Context

We are evolving Foundry Assured from a single-tenant, self-hosted product into a managed
SaaS where we are the orchestrator and each customer's data/compute stays in their own cloud
(BYO). Customers range from SMBs (want zero infra) to enterprises (demand full isolation).
A single tenancy model can't serve both well.

## Decision

Adopt the **Deployment Stamps pattern** in a **hybrid** configuration:

- **Shared stamp** (default, SMB): one multi-tenant control plane in *our* cloud serving N
  tenants; each tenant's data plane lives in the customer's cloud.
- **Dedicated stamp** (enterprise): a single-tenant control plane deployed into the
  customer's cloud (see [ADR-002](./ADR-002-dedicated-stamp-managed-app-lighthouse.md)).
- **Self-hosted** (existing): a single-tenant stamp the customer operates entirely — a
  special case of the dedicated stamp without our operation.

A stamp is an independent, isolated copy of the platform; adding stamps scales near-linearly
and contains blast radius.

## Consequences

- **+** Serves SMB and enterprise from one architecture; isolation is a deployment choice, not a rewrite.
- **+** The self-hosted product we ship today becomes a stamp variant — no fork.
- **−** We must operate and update multiple stamp types; requires a deployment-mode abstraction ([ADR-007](./ADR-007-coexistence-deployment-mode.md)).
- **−** Cross-stamp concerns (billing, global identity) need their own design later.

## Alternatives considered

- **Pure shared multi-tenant** — simplest, but no enterprise isolation; rejected.
- **Pure per-tenant stamps** — maximal isolation, but heavy ops for SMB and no economy of scale; rejected.

## Source (Microsoft guidance)

- [Deployment Stamps pattern](https://learn.microsoft.com/azure/architecture/patterns/deployment-stamp)
- [Tenancy models for a multitenant solution](https://learn.microsoft.com/azure/architecture/guide/multitenant/considerations/tenancy-models)
