---
title: Operate the SDLC board
description: Track work in-repo with the dna sdlc CLI — story-first, narrated, verified before close.
type: how-to
audience: contributor
status: stable
updated: 2026-07-11
---

# Operate the SDLC board

This repo tracks its own lifecycle as declarative DNA documents in `.dna/foundry-dev/` (the
dev-time **board scope** — distinct from the runtime prompt scope). Work is **story-first**: file
the Story before the work, narrate while building, verify before closing. The canonical agent
surface for this is [`AGENTS.md`](https://github.com/ruinosus/foundry-assured/blob/develop/AGENTS.md);
this page is the operator's quick reference.

## Setup (one-time per clone)

```bash
pip install "dna-cli>=0.3,<0.4"     # the `dna` binary
dna sdlc hooks install              # wire commit trailers (core.hooksPath = scripts/git-hooks)
```

The projected `dna-sdlc-cli` skill (`.claude/skills/`, `.github/skills/`, `.cursor/skills/`)
gives your AI coding agent the full workflow.

## The loop

```bash
dna sdlc brief                          # session start — what's in flight
dna sdlc story create s-my-work --feature f-x --desc "..." \
  --ac "Given/When/Then ..." --dod "code+tests+docs ..."   # AC + DoD required at create
dna sdlc story start s-my-work --plan-file plan.md          # the plan gate
dna sdlc story comment s-my-work --body "decided X because Y"  # narrate each meaningful step
dna sdlc test-guide create tg-my-work --verifies Story/s-my-work --step "run :: expect"
dna sdlc test-run record tg-my-work --outcome pass          # the test gate for done
dna sdlc story pr s-my-work --base develop  # gh pr create, pre-filled FROM the story
dna sdlc story done s-my-work           # only after the PR merges
```

While a story is active, every commit is stamped with `Work-Item:` + `dna-sdlc[bot]` trailers by
the versioned hook — the provenance seal linking git history to the work item
(`dna sdlc story commits s-my-work`).

## Rules

- **Base PRs on `develop`.** It's the gitflow integration line, promoted to `main` in batches
  (see [Branching model](../BRANCHING.md)). `--base develop` on `story pr`.
- **Never hand-edit `.dna/**.yaml` for status changes** — the CLI is the canonical write path so
  validation, timeline and journey events fire correctly.
- **Gapless done** — never mark `done` with a gap: finish to standard, or keep `in-progress` /
  decompose into tracked child stories. `story done` requires a passing TestRun.
- **Review = open PR; done = merged.** A story in `review` with no PR is stale.

The `dna eval` prompt-invariant suite and the assurance gates are the *product* gates that keep a
Story honest; this board is the *process* ledger that keeps the work traceable.
