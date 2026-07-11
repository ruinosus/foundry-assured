---
title: The .dna scopes
description: Two DNA scopes with two jobs — the dev-time SDLC board and the runtime prompt scope — and how they differ.
type: reference
audience: contributor
status: stable
updated: 2026-07-11
---

# The `.dna` scopes

The repo uses [DNA](https://github.com/ruinosus/dna) (Domain Notation of Anything) in **two
distinct places**. They share a format (typed YAML/Markdown documents) and a CLI (`dna`), but
serve unrelated purposes. Keep them straight.

| | Dev-time SDLC board | Runtime prompt scope |
|---|---|---|
| **Path** | `.dna/foundry-dev/` (repo root) | `apps/backend/app/.dna/<domain>/` |
| **Job** | track *how the repo is built* — Stories, Features, Plans, TestGuides/TestRuns | define *what the agents say* — declarative instructions the product composes |
| **Who reads it** | contributors + AI coding agents, via `dna sdlc` | the FastAPI backend at boot, via the DNA SDK |
| **How it changes** | `dna sdlc` CLI (never hand-edit for status) | edit the YAML + restart the process |
| **ADR** | the SDLC discipline (`AGENTS.md`) | [ADR-013](../adr/ADR-013-declarative-agent-prompts-dna.md) + [ADR-014](../adr/ADR-014-runtime-prompt-scope-no-rebuild.md) |

## The dev-time board — `.dna/foundry-dev/`

The repo tracks its own lifecycle as DNA documents: Stories, Features, Plans, TestGuides and
TestRuns under the `foundry-dev` scope. Work is story-first and every commit made while a story is
active is stamped with a `Work-Item:` trailer. Operate it with the
[SDLC how-to](../how-to/operate-sdlc.md); the canonical agent surface is `AGENTS.md`.

## The runtime prompt scope — `apps/backend/app/.dna/`

Agent instructions are **data, not code** ([ADR-013](../adr/ADR-013-declarative-agent-prompts-dna.md)):
one scope per domain (`helpdesk`, `cockpit`, `selfwiki`, `platform`), composed into prompts at
boot. Changing a prompt is a **file edit + restart, never an image rebuild**
([ADR-014](../adr/ADR-014-runtime-prompt-scope-no-rebuild.md)); in prod the scope is an Azure Files
share mounted at `/mnt/dna` selected via `DNA_BASE_DIR`. The prompt contracts are guarded by a
declarative eval suite (`dna eval run helpdesk-prompts --scope helpdesk`) that CI runs on every PR.
See [Update prompts without a redeploy](../how-to/update-prompts.md).
