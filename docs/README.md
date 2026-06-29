---
title: Documentation index
description: The map of every doc under docs/ — its type, audience, and what it's for.
type: reference
audience: contributor
status: stable
updated: 2026-06-27
---

# Documentation index

**Three domains, one mechanism.** The same assurance code drives three swappable knowledge
domains — **helpdesk** (fake runbooks), **cockpit** (Cockpit doc bundles), and **selfwiki**
(this repo's own deep-wiki) — each with its own knowledge base and ingest; deploy any subset.
Start with [METHOD.md](./METHOD.md) for what the mechanism guarantees, [DEPLOYMENT.md](./DEPLOYMENT.md)
to run it from zero (incl. the three ingests, app-role RBAC, and the two wiki-generation paths),
and the [RBAC plan](./RBAC-AND-USER-MANAGEMENT-PLAN.md) + [generated wiki](./wiki/README.md) for those pieces.

Every doc in this folder, with its type and audience, so you can find the one that fits your need.

| Doc | Type | Audience | What it's for |
| --- | --- | --- | --- |
| [METHOD.md](./METHOD.md) | reference | adopter | The assurance mechanism — what it guarantees, the gates, and how to run it. |
| [DEPLOYMENT.md](./DEPLOYMENT.md) | how-to | operator | End-to-end provisioning, from a fresh clone to a cloud-published deploy. |
| [IDENTITY-AND-ACCESS-SETUP.md](./IDENTITY-AND-ACCESS-SETUP.md) | reference | operator | The Entra ID map — what azd/Bicep creates vs the app registrations you set up by hand, and why. Read first when handing off. |
| [RBAC-AND-USER-MANAGEMENT-PLAN.md](./RBAC-AND-USER-MANAGEMENT-PLAN.md) | plan | contributor | App RBAC (Entra App Roles) + in-portal user management — company-groups→app-roles mapping, via Graph. |
| [USE-THIS-TEMPLATE.md](./USE-THIS-TEMPLATE.md) | how-to | adopter | Create your own repo from this template and wire up infra + CI/CD. |
| [CUSTOMIZE.md](./CUSTOMIZE.md) | how-to | adopter | Swap the four domain-specific pieces to adapt the showcase to your domain. |
| [RELEASE-AUTOMATION.md](./RELEASE-AUTOMATION.md) | how-to | operator | How a merge becomes a versioned release and a gated production deploy. |
| [USE-CASE-WALKTHROUGH.md](./USE-CASE-WALKTHROUGH.md) | explanation | evaluator | A worked, fictional example of the whole mechanism end to end. |
| [CASE-STUDY-LLM-WIKI-LOOP.md](./CASE-STUDY-LLM-WIKI-LOOP.md) | explanation | evaluator | A measured case study: ground both the docs and the eval in source. |
| [CASE-STUDY-SELFWIKI-DOGFOOD.md](./CASE-STUDY-SELFWIKI-DOGFOOD.md) | explanation | evaluator | Dogfooding the mechanism on this repo — two bugs it found in itself, and the genericity proof. |
| [wiki/](./wiki/README.md) | (generated) | evaluator | The machine-generated deep-wiki of this monorepo (the `selfwiki` domain corpus). |
| [deep-wiki-presentation.html](./deep-wiki-presentation.html) | (presentation) | evaluator | A standalone visual deck — how the deep-wiki is built, ingested, and what it costs (real run data). [Rendered via GitHub Pages](https://ruinosus.github.io/foundry-assured/deep-wiki-presentation.html). |
| [fluxo-deepwiki.html](./fluxo-deepwiki.html) | (presentation) | evaluator | The end-to-end flow — build-time (fidelity gate) × query-time (identity trim). [Pages](https://ruinosus.github.io/foundry-assured/fluxo-deepwiki.html). |
| [quadro-comparativo-deepwiki.html](./quadro-comparativo-deepwiki.html) | (presentation) | evaluator | Capability comparison vs other deep-wiki engines (DeepWiki SaaS, deepwiki-open, OpenDeepWiki). [Pages](https://ruinosus.github.io/foundry-assured/quadro-comparativo-deepwiki.html). |
| [ASSURANCE-MECHANISM-PLAN.md](./ASSURANCE-MECHANISM-PLAN.md) | plan | contributor | Design and rationale for the assurance mechanism and its intended work. |
| [SECOND-DOMAIN-WIKI-PLAN.md](./SECOND-DOMAIN-WIKI-PLAN.md) | plan | contributor | The living plan for adding a second domain via the LLM Wiki pattern. |
| [DOCS-STANDARD.md](./DOCS-STANDARD.md) | reference | contributor | How docs here are typed, structured, and diagrammed. |

For the conventions these docs follow — types, front-matter, and Mermaid diagrams — see [DOCS-STANDARD.md](./DOCS-STANDARD.md).
