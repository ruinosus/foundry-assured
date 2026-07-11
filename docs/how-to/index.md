---
title: How-to guides
description: Task-oriented recipes — deploy, template, customize, update prompts, run evals, operate the SDLC.
type: how-to
audience: operator
status: stable
updated: 2026-07-11
---

# How-to guides

Task-oriented recipes for getting a specific job done. Each assumes you already have the stack
running (see [Getting started](../getting-started/index.md)).

## Deploy & operate

- **[Deploy from zero](../DEPLOYMENT.md)** — end-to-end provisioning, from a fresh clone to a
  cloud-published deploy (infra, Entra app registrations, KB/memory, hosted agent, Container Apps).
- **[Release & gated deploy](../RELEASE-AUTOMATION.md)** — how a merge becomes a versioned release
  and a gated production deploy (release-please + the GitHub App).
- **[Package the dedicated stamp](../D-PACKAGING-RUNBOOK.md)** — build the Managed Application +
  Lighthouse dedicated stamp and the hosted platform agent.

## Adapt it

- **[Use this as a template](../USE-THIS-TEMPLATE.md)** — create your own repo from this one and
  wire up infra + CI/CD identities.
- **[Swap in your own domain](../CUSTOMIZE.md)** — replace the corpus, prompts, action and identity
  to turn this into any "ask → ground → resolve → escalate" assistant.

## Run it day-to-day

- **[Update prompts without a redeploy](update-prompts.md)** — edit a declarative prompt YAML and
  refresh the running agent with a restart, not an image rebuild (ADR-014).
- **[Run the evals](run-evals.md)** — the offline policy gate, the cloud LLM-judge scores, and the
  planted-violation self-test.
- **[Operate the SDLC board](operate-sdlc.md)** — track work in-repo with `dna sdlc`.
