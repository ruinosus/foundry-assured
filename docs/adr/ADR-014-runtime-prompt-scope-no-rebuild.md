# ADR-014 — The runtime prompt scope decouples from the image (volume mount; restart, not rebuild)

- **Status:** Proposed
- **Date:** 2026-07-10 (production/ACA leg added the same day)
- **Context:** [ADR-013](./ADR-013-declarative-agent-prompts-dna.md) phase 3 —
  [`apps/backend/compose.yaml`](../../apps/backend/compose.yaml),
  [`apps/backend/Dockerfile`](../../apps/backend/Dockerfile),
  [`apps/backend/app/agents/prompts.py`](../../apps/backend/app/agents/prompts.py),
  [`infra/containerapps.bicep`](../../infra/containerapps.bicep),
  [`scripts/push-prompts.sh`](../../scripts/push-prompts.sh)

## Context

ADR-013 moved the agent prompts into the declarative DNA scope at
`apps/backend/.dna/helpdesk/`, but the scope still ships **inside the image**
(`COPY .dna ./.dna`). Editing one word of a prompt therefore still costs a
container build: the YAML is data, but it travels like code. ADR-013 already
named the gap ("once a runtime reload/refresh path is wired, no deploy").

Two distinct `.dna/` trees exist in this repo and this ADR is only about the
second one:

| Tree | Role | Lifecycle |
|------|------|-----------|
| `.dna/foundry-dev/` (repo root) | **Dev-time** SDLC board (features/stories/test-runs) | Versioned artifact of how we WORK; never deployed |
| `apps/backend/.dna/` | **Runtime** prompt scope the backend composes at boot | What the product RUNS; ships with the backend |

## Decision

**Bind-mount the working-tree scope over the baked-in copy for local container
runs, keep the `COPY` as the self-contained fallback, and define the refresh
unit as a process restart — not a hot reload.**

- **Volume, not a new distribution channel** — `apps/backend/compose.yaml`
  mounts `./.dna` read-only at `/app/.dna`, shadowing the image copy. A prompt
  edit on the host is picked up by `docker compose restart backend`: restart,
  **no rebuild, no new image**. Without the mount the image still runs
  self-contained (azd/ACA path unchanged), and a missed `COPY` still fails
  loudly at boot (ADR-013's fail-loud shim).
- **Restart is the honest refresh unit.** `prompts.py` composes the constants
  once at import and `domains.py`/the workflow build the agents at boot;
  `dna-sdk` 0.1.0 has no in-process scope watcher, and even a per-request
  recomposition would not reach agents already constructed with the old text.
  Wiring a hot-reload would mean restructuring the shim *and* rebuilding
  agents mid-flight — a redesign, not a mount. Restart-on-edit resolves the
  real case (prompt iteration without an image build) with machinery the SDK
  already supports: `Kernel.quick()` re-reads the scope from disk on every
  process boot.
- **Production (ACA) twin — Azure Files share at an ALTERNATIVE path, selected
  by one env var.** The backend container app mounts the `assured-prompts`
  share (same storage account as the tickets share, same
  `managedEnvironments/storages` pattern, but `ReadOnly`) at **`/mnt/dna`** —
  deliberately *not* over `/app/.dna` — and `DNA_BASE_DIR=/mnt/dna` selects it.
  `prompts.py` resolves the scope directory with asymmetric semantics:
  - env var **unset** → the baked-in copy, byte-identical to before (local
    dev, compose, self-contained image);
  - env var set but the scope **absent** there (a fresh provision's empty
    share — nobody has published yet) → loud log + fall back to the baked
    copy: a fresh `azd up` must never crash-loop the backend;
  - env var set and the scope **present** → it wins, and a broken scope fails
    the boot loudly (ADR-013). Present means an operator published; a silent
    fallback would run stale prompts while they believe the new ones are live.

  Why not mount over `/app/.dna` like compose does: a compose *bind mount*
  projects a host directory that already HAS the content, but an ACA Azure
  Files volume **shadows the image path with the share's content** — an empty
  share would erase the baked scope and the fail-loud shim would crash-loop
  the backend until an out-of-band seed step ran, making provisioning
  order-dependent. The alternative path keeps "empty share" a non-event and
  makes adopting the external scope an explicit, observable act (the boot log
  says which source won).

  The prod loop (scripted in [`scripts/push-prompts.sh`](../../scripts/push-prompts.sh)):
  *edit YAML → `dna eval run helpdesk-prompts` → upload to the share →
  `az containerapp revision restart`* — no image build, no `azd deploy`.
  Restart stays the refresh unit, exactly as below; with scale-to-zero the
  restart degrades to "next cold start picks it up". `upload-batch` never
  deletes: removing/renaming a scope file needs the script's `--mirror` mode.
- **Postgres source is the documented evolution, not this change.** The SDK
  ships a Postgres source adapter (`DNA_SOURCE_URL`) that would move the scope
  out of the filesystem entirely — the right shape once multiple replicas must
  agree on prompt versions and edits need an authoring surface instead of a
  git checkout. Deliberately **not** implemented here: it adds a database to
  the deployment for a problem (multi-replica coherence) the pilot does not
  have yet. When it lands, the volume mount retires naturally — the base_dir
  becomes a source URL.

## Alternatives considered

- **Keep rebuilding the image per prompt edit (status quo).** Rejected — this
  is the deploy-coupling ADR-013 set out to remove; only the last hop was
  missing.
- **Hot reload (watchdog / per-request recomposition / `DNA_RELOAD=1`).**
  Rejected for now: agents are constructed at boot from the composed
  constants, so an in-process reload gives a false promise unless the agent
  wiring is also rebuilt per request. Restart-grade refresh is what the
  current architecture honestly supports.
- **Azure Files mounted OVER `/app/.dna` (shadowing, like compose does).**
  Rejected — see the production-leg bullet in the Decision: on ACA the mount
  replaces the image directory with the share content, so an unseeded share
  erases the baked scope and crash-loops the boot; provisioning would depend
  on an out-of-band seed step. The alternative-path + `DNA_BASE_DIR` design
  keeps the image self-contained and the adoption explicit.
- **Jump straight to the Postgres source.** Deferred as above — right
  endgame, wrong first step for a single-replica pilot.

## Consequences

- **+** Prompt iteration cost drops to *edit YAML → restart container*; the
  image is rebuilt only when code or dependencies change.
- **+** The dev-time/runtime split is now explicit (table above) — the board
  and the product scope stop being conflated just because both live in `.dna/`.
- **+** The eval guard (`dna eval run helpdesk-prompts`, CI) keeps gating
  prompt *content* regardless of how the scope reaches the process.
- **+** Production now has the same property: the ACA backend reads the scope
  from the `assured-prompts` share (`DNA_BASE_DIR=/mnt/dna`), so a prod prompt
  change is *push-prompts.sh → revision restart* — the image rebuilds only for
  code. The dedicated stamp (`infra/managed-app/`) inherits this for free: it
  composes the same `containerapps.bicep`/`resources.bicep` modules.
- **−** Prompt state in prod now lives in TWO places with explicit precedence:
  the share wins when it holds the scope, the baked copy is the fallback. The
  boot log states which source won; drift is bounded by publishing from the
  repo (`push-prompts.sh` uploads the working tree, whose content CI gates
  with the eval suite).
- **−** Restart-grade refresh means a brief interruption on prompt updates —
  acceptable for the pilot; the Postgres-source evolution is where zero-drop
  updates would live.

## References

- [ADR-013](./ADR-013-declarative-agent-prompts-dna.md) — the declarative
  prompt move this completes
- [`apps/backend/compose.yaml`](../../apps/backend/compose.yaml) — the mount +
  the loop, documented inline
- [DNA — declarative agent DNA SDK](https://github.com/ruinosus/dna) ·
  `dna-sdk` 0.1.0 on PyPI (filesystem + Postgres source adapters)
