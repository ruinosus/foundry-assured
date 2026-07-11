---
title: Update prompts without a redeploy
description: Edit a declarative agent prompt and refresh the running agent with a restart, not an image rebuild.
type: how-to
audience: operator
status: stable
updated: 2026-07-11
---

# Update prompts without a redeploy

Agent instructions are **declarative data**, not code — they live as YAML/Markdown in the
runtime DNA scope under `apps/backend/app/.dna/<domain>/`
([ADR-013](../adr/ADR-013-declarative-agent-prompts-dna.md)). Changing what an agent says is a
**file edit + a process restart**, never an image rebuild
([ADR-014](../adr/ADR-014-runtime-prompt-scope-no-rebuild.md)).

> [!IMPORTANT]
> This is the **runtime prompt scope** (`apps/backend/app/.dna/`), which is a different thing
> from the **dev-time SDLC board** (`.dna/foundry-dev/` at the repo root). Editing prompts touches
> the former; tracking work touches the latter. See [The `.dna` scopes](../reference/dna-scopes.md).

## Why a restart, not hot reload

Prompts compose at **import** and agents are built at **boot** — so an in-process hot reload
would be a false promise (already-built agents don't re-read their instruction). The honest
refresh unit is a process restart. A backend scaled to zero needs no restart at all: the next
cold start reads the fresh scope.

## Local

The compose stack bind-mounts the scope read-only over the baked-in copy, so an edit on the host
is visible to the container on restart:

```bash
$EDITOR apps/backend/app/.dna/helpdesk/agents/cockpit.yaml   # edit the instruction
dna eval run helpdesk-prompts --scope helpdesk               # the content gate (CI runs it too)
# restart the process (uvicorn --reload picks up module reloads; for the composed
# prompt, restart the process): Ctrl-C and re-run, or restart the compose service.
```

## Production (Azure Container Apps)

In prod the scope is an **Azure Files share** mounted read-only at `/mnt/dna`, selected via
`DNA_BASE_DIR`; the baked-in copy is the fallback. `scripts/push-prompts.sh` uploads the scope
and restarts the backend revision — **no `azd deploy`, no image build**:

```bash
$EDITOR apps/backend/app/.dna/helpdesk/agents/cockpit.yaml
dna eval run helpdesk-prompts --scope helpdesk   # gate the change before publishing
./scripts/push-prompts.sh                        # upload to the share + restart the revision
```

> [!WARNING]
> `push-prompts.sh` overwrites but never **deletes**: removing or renaming a scope file needs
> `--mirror` (which empties the share first) or an explicit `az storage file delete-batch`.
> During a `--mirror` wipe→upload window a cold start boots on the baked-in fallback; the
> terminal restart settles it.

## Verify

Compose the prompt before and after and diff it — the change should appear with no image built:

```bash
cd apps/backend
uv run python -c "from app.agents import prompts; print(prompts.COCKPIT_INSTRUCTIONS)"
```

The prompt-invariant eval suite (`dna eval run helpdesk-prompts --scope helpdesk`) is the guard
of record for prompt contracts and runs in CI on every PR.
