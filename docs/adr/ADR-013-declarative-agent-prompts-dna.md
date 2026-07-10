# ADR-013 — Agent instructions become declarative data (DNA), not deploy-coupled code

- **Status:** Proposed
- **Date:** 2026-07-10
- **Context:** [`apps/backend/app/agents/prompts.py`](../../apps/backend/app/agents/prompts.py) and every agent built from it (workflow triage/retrieve/resolve, both concierge variants, cockpit, selfwiki, platform)

## Context

All nine agent instruction blocks were hardcoded Python constants in
`app/agents/prompts.py`. That made the file an honest single source of truth
(CONTRIBUTING even pins the rule), but it couples **prompt iteration to a code
deploy**: changing one word of the cockpit answering discipline means branch →
PR → CI → container build → `azd` deploy. Prompts are the highest-churn,
lowest-risk artifact in the system — and the only one that could not change
without shipping a new image.

Two adjacent pressures make this worse over time:

1. **The prompts already have consumers beyond the backend process** — the
   self-contained hosted-agent containers mirror the workflow prompts by hand,
   and the eval layer (`eval/assertions.py`, golden datasets) encodes
   expectations about their content. Nothing machine-checks that the prompt an
   agent runs with still satisfies the contracts the rest of the system
   branches on (e.g. the RESOLVE `TICKET:` sentinel, the grounded citation
   duty that rule 4 + the ASSERT policy gate assume).
2. **The SaaS direction (ADR-001/006/007/010) wants per-tenant variation.**
   Deployment modes and tenant entitlement are already data-driven; prompts
   are the remaining behavior that a `dedicated`/`shared` operator cannot vary
   per tenant without forking code.

[DNA](https://github.com/ruinosus/dna) is a microkernel SDK for exactly this
externalization: agent behavior (instructions, skills, evals) lives as
YAML/Markdown documents in a `.dna/<scope>/` directory, loaded and composed at
runtime, with layer/tenant overlay machinery and an offline eval runner. It
was pre-release (no PyPI dist) when this ADR landed — installable only as a
commit-pinned git dependency; since then `dna-sdk`/`dna-cli` `0.1.0` shipped
on PyPI and the backend consumes the official package (see Dependency below).
This repo is its **first external consumer** — a deliberately small pilot:
prove the loop (declare → compose → verify), do not redesign any prompt.

## Decision

**Move the nine instruction texts into a declarative DNA scope at
`apps/backend/.dna/helpdesk/` (one `Agent` document per former constant) and
turn `prompts.py` into a composition shim — same nine public constants, zero
consumer changes, guarded by a byte-equivalence gate and a prompt-invariant
eval suite in CI.**

- **Scope layout** — `.dna/` lives **inside `apps/backend/`**, not the repo
  root: the backend is the only consumer, the directory ships with the
  backend's Docker build context (one `COPY .dna ./.dna` line), and the
  monorepo root stays uncluttered. `Genome.yaml` roots the scope; agents are
  `agents/{triage,retrieve,resolve,concierge-base,concierge-grounded,concierge-ungrounded,cockpit,selfwiki,platform}.yaml`.
- **Byte fidelity over elegance** — every `instruction` is the exact former
  constant text. We deliberately did **not** decompose the concierge family
  into a DNA Soul + variants, even though the structure is natural (base
  persona + grounded/ungrounded suffixes): the original composition joins with
  a single space on one line, which DNA's section-based prompt composition
  cannot reproduce byte-identically. The base sentence is therefore duplicated
  inline in both variants (as it already was at runtime), and `concierge-base`
  remains its own document because the constant is part of the public surface.
  Decomposition is a candidate follow-up once the pilot loop is trusted.
- **The shim** — `prompts.py` loads the scope once at import
  (`Kernel.quick("helpdesk", base_dir=…)`) and assigns each constant from
  `build_prompt(agent=…)`. Composition cost is paid once per process, exactly
  like the former constants. It is **fail-loud**: missing package, missing
  `.dna` directory, scope load failure, or an empty composed prompt all raise
  `RuntimeError` at import — the backend refuses to boot rather than run an
  agent with a blank instruction. The single normalization is a documented
  `rstrip("\n")` (DNA pads empty composition sections with trailing newlines;
  the constants never carried one).
- **Dependency** — `dna-sdk` is added to the backend's runtime dependencies
  from **PyPI as `dna-sdk>=0.1,<0.2`** (official release); upgrades are
  explicit lockfile diffs within the minor range. Its transitive deps are
  light (pyyaml, chevron, aiofiles, jsonschema, typing_extensions). The
  backend image gains the `COPY .dna` line.
  *Historical note:* DNA was pre-release when this ADR landed, so the pilot
  first consumed a commit-pinned git dependency
  (`3628a9ee…#subdirectory=packages/sdk-py` — the pin *was* the version),
  which also required hatch `allow-direct-references` and `git` inside the
  slim image. With `dna-sdk 0.1.0` on PyPI all three artifacts of that
  workaround were removed; the composed prompts were verified byte-identical
  between the pinned SHA and the 0.1.0 release before switching.
- **Evals as the guard, two layers, both in the required CI check:**
  1. `eval/prompts_equivalence_test.py` — pins the nine **original texts as a
     golden fixture** and proves each composed constant is byte-equal. A
     legitimate prompt change must update golden + YAML in the same PR, so the
     diff always shows the prompt change explicitly.
  2. `.dna/helpdesk/eval-{cases,suites}/` — nine offline `EvalCase`s asserting
     the **contracts** each prompt carries (TICKET sentinel, `NO_MATCH`
     sentinel, cite-every-claim, pt-BR + KB-exclusive grounding, never-claim-a-
     write). Run in CI via `dna eval run helpdesk-prompts` with `dna-cli`
     from PyPI (exit 1 on any failing case; planted-violation verified
     locally). Unlike the equivalence gate, this layer keeps guarding
     once prompts legitimately start evolving in `.dna/`.

`prompts.py` stays the single **consumption** point (the CONTRIBUTING rule
holds); authoring moves to `.dna/helpdesk/agents/`.

## Alternatives considered

- **Keep hardcoded constants (status quo).** Simple, but prompt iteration
  stays deploy-coupled and per-tenant prompt variation has no path. Rejected —
  this is the problem.
- **Env vars / app settings for prompts.** Deploy-decoupled, but multiline
  prose in env vars is unmanageable, unversioned, undiffable, and has no
  composition/eval story. Rejected.
- **Foundry-side prompt management (hosted agent definitions).** Right for the
  hosted-agent packaging, but the in-process workflow agents don't run there,
  and it offers no offline eval of the composed text. Complementary, not a
  replacement.
- **A hand-rolled `prompts.yaml` + `yaml.safe_load`.** Minimal dependency,
  but reinvents what DNA already provides (typed Kinds, scope/tenant overlay
  machinery for the SaaS direction, the offline eval runner + CLI) and gives
  this pilot no leverage. Rejected — the point of the pilot is to consume the
  SDK, and the SDK's overlay engine is the concrete path to ADR-006/010-style
  per-tenant prompts.
- **Full decomposition into Soul/Guardrail Kinds now.** More elegant, but
  cannot be byte-faithful (separator semantics) and turns a mechanical move
  into a prompt redesign. Deferred.

## Consequences

- **+** Prompt edits are YAML diffs; no Python changes, and (once a runtime
  reload/refresh path is wired) no deploy. Today the composition still happens
  at import, so a restart picks up changes — already a strict improvement over
  rebuild+redeploy for config-only updates.
  *Phase 3:* [ADR-014](./ADR-014-runtime-prompt-scope-no-rebuild.md) closes
  the local half of this gap — the compose run bind-mounts the scope over the
  image copy, so a prompt edit costs a restart, not a rebuild.
- **+** Prompt contracts are now machine-checked in the required CI gate, in
  both directions: accidental drift (byte gate) and contract regressions
  (invariant suite).
- **+** A concrete path to per-tenant prompt overlays in the `shared`/
  `dedicated` modes via DNA's layer/tenant machinery — aligned with
  ADR-006/ADR-010 rather than a parallel mechanism.
- **−** A new runtime dependency on a young SDK (now an official PyPI
  release, `dna-sdk>=0.1,<0.2`). Mitigated: range-pinned via the lockfile,
  light transitive deps, fail-loud boot, and the shim keeps the public
  surface — reverting is "inline the golden fixture back".
- **−** The backend image must ship `.dna/` (a missed `COPY` fails loudly at
  boot, not silently). (The build-time `git` requirement died with the
  git-dep — see the Dependency historical note.)
- **−** The hosted-agent containers still mirror prompts by hand (unchanged by
  this ADR); the mirror-drift risk noted in `prompts.py`'s docstring remains a
  follow-up.
- **Neutral:** the CONTRIBUTING "prompts change only in `prompts.py`" rule is
  restated as "prompts change only in `.dna/helpdesk/agents/`"; the file
  itself remains the only consumption point.

## Addendum — Phase 2 (decomposition, the deferred follow-up)

With the phase-1 move merged and the loop trusted, the deferred decomposition
happened (tracked in-repo as `Story/s-decompose-prompts` on the
`.dna/foundry-dev` board):

- **Soul** — the shared concierge persona lives once in `souls/concierge/`
  (soulspec bundle); `concierge-grounded`/`concierge-ungrounded` reference it
  (`spec.soul`) and keep only their variant delta in `instruction`. The
  `concierge-base` agent — and the `CONCIERGE_BASE_INSTRUCTIONS` constant —
  died: nothing consumed them standalone; the persona IS the Soul now.
- **Guardrails** — cross-cutting rules became `Guardrail` documents wired via
  `spec.guardrails`: `grounded-citation` (cite-every-claim + cite-or-don't-
  know, on the grounded variant) and `no-write-claims` (the HITL
  never-claim-a-write rule, on the platform concierge). Both `severity: error`,
  `scope: output`, rendered as `## Guardrail:` sections in the composed prompt.
- **The guard changed nature** — the byte-equivalence gate
  (`eval/prompts_equivalence_test.py`) retired: it existed to prove the *move*
  was faithful, and by definition dies the moment prompts legitimately evolve.
  The eval suite is now the guard of record, extended with **negative
  invariants** the byte paradigm could not express (`not_contains`: the
  ungrounded variant must NOT carry the citation duty), plus checks that the
  guardrails are actually *wired* (the rendered section header), and
  `concierge-soul-identity` targeting the Soul directly as a prompt target.
  Planted-violation (guardrail unwired) → `dna eval run` exit 1, re-verified.
- **Consumers unchanged** — `prompts.py` composes the same public constants
  (minus the dead `CONCIERGE_BASE_INSTRUCTIONS`); the composed texts are now
  multi-part prompts rather than byte-copies.

## References

- [DNA — declarative agent DNA SDK](https://github.com/ruinosus/dna) · [docs](https://ruinosus.github.io/dna/)
- [ADR-006](./ADR-006-tenant-scoped-config.md), [ADR-007](./ADR-007-coexistence-deployment-mode.md), [ADR-010](./ADR-010-per-tenant-domain-entitlement.md) — the tenant-scoped, data-driven direction this extends to prompts
- [`.dna/helpdesk/eval-suites/helpdesk-prompts.yaml`](../../apps/backend/.dna/helpdesk/eval-suites/helpdesk-prompts.yaml) — the prompt-contract guard of record (phase 2 retired the byte-equivalence gate)
