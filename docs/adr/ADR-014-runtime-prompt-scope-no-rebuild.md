# ADR-014 — The runtime prompt scope decouples from the image (volume mount; restart, not rebuild)

- **Status:** Proposed
- **Date:** 2026-07-10
- **Context:** [ADR-013](./ADR-013-declarative-agent-prompts-dna.md) phase 3 —
  [`apps/backend/compose.yaml`](../../apps/backend/compose.yaml),
  [`apps/backend/Dockerfile`](../../apps/backend/Dockerfile),
  [`apps/backend/app/agents/prompts.py`](../../apps/backend/app/agents/prompts.py)

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
- **Azure Files mount on the Container App (cloud twin of this decision).**
  Compatible and likely the production continuation (ACA supports volume
  mounts), but it is an infra change with its own provisioning story —
  follow-up, not this ADR.
- **Jump straight to the Postgres source.** Deferred as above — right
  endgame, wrong first step for a single-replica pilot.

## Consequences

- **+** Prompt iteration cost drops to *edit YAML → restart container*; the
  image is rebuilt only when code or dependencies change.
- **+** The dev-time/runtime split is now explicit (table above) — the board
  and the product scope stop being conflated just because both live in `.dna/`.
- **+** The eval guard (`dna eval run helpdesk-prompts`, CI) keeps gating
  prompt *content* regardless of how the scope reaches the process.
- **−** The mount only exists where compose (or an equivalent volume) is used;
  the azd/ACA deployment still bakes the scope and needs a redeploy for
  prompt changes until the Azure Files (or Postgres source) follow-up lands.
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
