---
title: Foundry Assured — documentation
description: The navigable docs for Foundry Assured — a Microsoft Foundry assurance showcase and multi-tenant SaaS.
type: reference
audience: adopter
status: stable
updated: 2026-07-11
---

# Foundry Assured

**A Microsoft Foundry showcase with measured guarantees.** An internal engineering-support
**concierge**: a developer asks in chat → the system **triages** intent → **retrieves** from a
grounded knowledge base → **resolves** with a cited answer → **escalates** with human approval
when an action is needed — every answer **evaluated** and **traceable**. On top of the showcase
it ships a reusable **assurance mechanism** (each guarantee a CI-gated number, not a promise) and
a **hybrid multi-tenant SaaS** seam — one codebase, three deployment modes.

The frontend is **CopilotKit** (Next.js) over the **AG-UI** protocol; the backend is Python
(**FastAPI** + `agent-framework`) calling **Microsoft Foundry** in the cloud.

## Start here

These docs follow the [Diátaxis](https://diataxis.fr/) framework — four kinds of documentation,
each with one job. (Every page is typed the same way in its front-matter; see the
[documentation standard](DOCS-STANDARD.md).)

<div class="grid cards" markdown>

- :material-school: **[Tutorials](getting-started/index.md)**

    Learning-oriented. Bring up the stack locally and run your first grounded helpdesk
    flow — with **no Azure** in demo mode, or end-to-end against Foundry.

- :material-wrench: **[How-to guides](how-to/index.md)**

    Task-oriented. [Deploy](DEPLOYMENT.md), [use this as a template](USE-THIS-TEMPLATE.md),
    [swap in your own domain](CUSTOMIZE.md), [update prompts without a redeploy](how-to/update-prompts.md),
    [run the evals](how-to/run-evals.md), and [operate the SDLC board](how-to/operate-sdlc.md).

- :material-file-document: **[Reference](reference/index.md)**

    Information-oriented. The [assurance mechanism](METHOD.md), the
    [architecture](reference/architecture.md) (domains, agents, flow),
    [configuration](reference/configuration.md), the [`.dna` scopes](reference/dna-scopes.md),
    identity, cost.

- :material-lightbulb-on: **[Explanation](explanation/index.md)**

    Understanding-oriented. The [ADRs](adr/README.md), the multi-tenant SaaS model, the DNA
    prompt integration, and the measured case studies that prove the mechanism generalizes.

</div>

## What makes it different

The headline is the **assurance mechanism**: point an agent at one or more repos / knowledge
bases and get **measured, gated** guarantees. Each pillar is a number wired to a CI gate.

| Pillar | Guarantee | Gate |
|---|---|---|
| **Build** | every wiki claim cites a real source file | fidelity gate (`wiki_builder`) |
| **Recall** | nothing relevant is left out of retrieval | recall measured (agentic effort) |
| **Completeness** | answers are grounded *and* complete | completeness gate (`run_eval`) |
| **Access control** | each caller sees only their entitlement — access **follows the source** | access-control gate (violations = 0) |
| **Red-team** | no prompt leaks content across groups | red-team gate (ASR ≤ ceiling) |

Full as-built model: **[the assurance mechanism](METHOD.md)**.

## Three deployment modes

One codebase, a deployment-mode seam ([ADR-007](adr/ADR-007-coexistence-deployment-mode.md)):
**self_hosted** (single-tenant, today's default), **dedicated** (Azure Managed Application +
Lighthouse in the customer's subscription), and **shared** (multi-tenant, tenant resolved
per-request from the Entra `tid`). All data, compute and credentials stay in the customer's
cloud — the control plane stores per-tenant config + connection references only, **never
secrets** ([ADR-005](adr/ADR-005-never-store-secrets.md)). See the
[SaaS model](explanation/index.md#the-multi-tenant-saas-model).
