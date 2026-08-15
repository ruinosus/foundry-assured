# Wiki refresh loop

Consult this page when changing the self-wiki maintenance pipeline: the workflows in `.github/workflows/`, the adapter in `apps/backend/app/knowledge/adapt_openwiki.py`, or the acceptance checks in `apps/backend/eval/`.

This workflow implements the architecture described in the wiki automation decision: OpenWiki owns regeneration, but this repository still owns the trigger, the bundle format, and the acceptance gate.

<!-- openwiki: mermaid parse failed and this diagram was converted to a text fence so it does not break rendering. Fix the diagram source and restore the mermaid fence. Parser error: Heuristic: an unescaped angle bracket inside a label breaks rendering; rephrase the label. -->
```text
flowchart LR
  A[Source changes on main] --> B[wiki-freshness.yml]
  B -->|stale=false| C[No regen]
  B -->|stale=true| D[wiki-regen.yml]
  D --> E[openwiki code --update]
  E --> F[adapt_openwiki.py]
  F --> G[docs/wiki/<component>/<version>]
  G --> H[wiki_fidelity_test.py]
  H -->|pass| I[create-pull-request]
  H -->|fail| J[Stop before review or ingest]
```

*Runtime flow: deterministic freshness decides whether OpenWiki runs; repository-owned adaptation and fidelity checks decide whether the result is reviewable.*

## Freshness signal

`wiki-freshness.yml` is no longer a per-PR status light. The workflow comment explains why: once regeneration is automated, a PR check would become green merely because a bot touched the wiki, which is the same "always-on, no information" problem as the old always-red state.

The workflow now has four entry modes:

- `push` to `main`,
- weekly `schedule`,
- `workflow_dispatch`,
- and `workflow_call`, which exposes a single output: `stale`.

The implementation seam is the `freshness` job in `.github/workflows/wiki-freshness.yml`, which runs `uv run python -m eval.wiki_freshness_test` from `apps/backend`. The Python check in `apps/backend/eval/wiki_freshness_test.py`:

- maps bundle component names to source roots through `_AREA`,
- reads each committed `docs/wiki/**/manifest.json`,
- compares `generatedAt` to the latest Git commit touching the corresponding source area via `_latest_commit_iso()`,
- and returns non-zero only when a bundle is older than its source.

The workflow intentionally converts that non-zero result into `stale=true` instead of a failed job. That invariant matters if you edit either side: **drift is data for the caller, not itself an operational failure**.

### Focused change points

Concept -> Public API -> Implementation -> Tests:

- Drift status -> `workflow_call.outputs.stale` -> `.github/workflows/wiki-freshness.yml` `steps.check` -> `apps/backend/eval/wiki_freshness_test.py`
- Source-to-bundle ownership -> `_AREA` mapping -> `apps/backend/eval/wiki_freshness_test.py` -> same file, exercised by running the module

### Minimal validation

- Focused: `cd /home/runner/work/foundry-assured/foundry-assured/apps/backend && uv run python -m eval.wiki_freshness_test`
- Conditional, broader: re-run the GitHub workflow only when changing workflow-call wiring or trigger conditions.

## Regeneration workflow

`wiki-regen.yml` consumes the freshness output instead of duplicating the drift logic. The `drift` job calls `./.github/workflows/wiki-freshness.yml`; the `regen` job is gated by `needs.drift.outputs.stale == 'true' || inputs.force`.

Inside `regen`, the workflow:

1. checks out full Git history so `openwiki code --update` can diff against the prior documented commit,
2. installs pinned `openwiki@0.3.3`,
3. runs `openwiki code --update --print --modelId "${{ vars.OPENWIKI_MODEL }}"`,
4. adapts `openwiki/` output into `docs/wiki` via `uv run python -m app.knowledge.adapt_openwiki`,
5. enforces the fidelity floor through `uv run python -m eval.wiki_fidelity_test --component "foundry-helpdesk-$AREA"`,
6. and only then opens a PR with `peter-evans/create-pull-request@v7`.

The workflow is deliberately `workflow_dispatch`-only today. The ADR-backed reason is recorded in comments and in the wiki automation decision: repeated unchanged runs still produced minor agent revisions, so a daily cron would create review noise until real no-op behavior is proven.

### Required configuration

The operational setup is documented in `CONTRIBUTING.md` and used directly in the workflow:

- Variables: `OPENWIKI_BASE_URL`, `OPENWIKI_MODEL`
- Secret: `OPENWIKI_API_KEY`
- Provider seam: `OPENWIKI_PROVIDER=openai-compatible`
- Telemetry opt-outs: `OPENWIKI_TELEMETRY_DISABLED=1`, `DO_NOT_TRACK=1`

The workflow comments also record an important runtime invariant: OpenWiki has no `azure` provider, so Azure OpenAI is reached through its OpenAI-compatible `/openai/v1` surface.

### Focused tests and checks

There is no dedicated workflow-unit test file in the repository, so validation is split by boundary:

- workflow syntax and control flow: inspect `.github/workflows/wiki-regen.yml`,
- generated-artifact acceptance: `apps/backend/eval/wiki_fidelity_test.py`,
- manifest shape compatibility: `apps/backend/eval/docbundle_contract_test.py`.

That split matters for future changes: a workflow edit is not complete if only the YAML looks right. The resulting bundle still has to pass the consumer-facing gates below.

## Adapter and bundle invariants

`apps/backend/app/knowledge/adapt_openwiki.py` is the seam between OpenWiki's OKF output and the repository's established ingest bundle format. It exists because the self-wiki knowledge base still consumes `docs/wiki/<component>/<version>/{manifest.json,pages/page-N.md,llms.txt}` rather than raw `openwiki/*.md` pages.

### What the adapter preserves

- **Commit provenance:** `_run_receipt()` reads `openwiki/.last-update.json`, and the manifest `source.commit` is set from `gitHead` there rather than from current HEAD.
- **Producer identity:** manifest `model` is written as `openwiki/<receipt.model>` so OpenWiki output stays distinguishable from other generation paths.
- **Navigation order:** `_ordered_pages()` follows `index.md` links first, then appends unlinked content pages in sorted order so content is not silently dropped.

### What the adapter intentionally strips or rewrites

- **OKF front matter:** `_split_front_matter()` removes it from page bodies after extracting a title, because bundle retrieval should not ingest transport metadata.
<!-- openwiki: broken internal link [page.md] file "page.md" does not exist. Fix the href or restore the target, then delete this comment. -->
- **Internal wiki links:** `_flatten_internal_links()` turns `text` into plain text. The code comment explains why: the fidelity regex would otherwise misread inter-page links as source-file citations and inflate the score.
- **Scaffold and navigation files:** `_SKIP_NAMES` excludes `index.md`, `_skeleton.md`, `_plan.md`, `instructions.md`, `log.md`, and `readme.md`; `_SKIP_DIRS` excludes `.git` and `node_modules`.

### Manifest contract boundary

The adapter does not invent a parallel schema. After building the manifest, it calls `validate_manifest()` from `apps/backend/app/knowledge/docbundle_schema.py`, which validates against the vendored `docbundle.schema.json` contract.

That contract is also guarded by `apps/backend/eval/docbundle_contract_test.py`. If you add a field to the adapter, the change surface is larger than one Python file:

1. adapter manifest construction,
2. schema contract in `docbundle.schema.json` if the field is truly part of the shared format,
3. any readers listed in `docbundle_contract_test.py`,
4. and the committed bundle artifacts if you are testing the path end to end.

### Minimal validation

- Adapter/schema boundary: `cd /home/runner/work/foundry-assured/foundry-assured/apps/backend && uv run python -m eval.docbundle_contract_test`
- Conditional broader check: run the regeneration workflow only when you changed page ordering, skip rules, or manifest content and need to see a real generated bundle.

## Fidelity gate

`apps/backend/eval/wiki_fidelity_test.py` exists for bundles generated **outside** `wiki_builder.py`. Instead of re-implementing correctness, it imports `wiki_builder._fidelity_report()`, `_fidelity_floor()`, and `gather_source()`.

That reuse creates an important external contract:

- **Internal correctness:** `adapt_openwiki.py` can write files and validate JSON schema.
- **Shipped-surface correctness:** the produced bundle still must meet `build.fidelity_min` in `apps/backend/eval/assurance.yaml` and contain zero worktree citations before it is safe for ingest.

The gate reads the latest bundle for a component unless `--version` is supplied, loads every `pages/*.md` file, and fails in two cases:

- any citation points into a worktree,
- or the resolved-citation score is below the configured floor.

Because it reuses `_fidelity_report()`, changes to citation parsing in `apps/backend/app/knowledge/wiki_builder.py` affect both the original generator and OpenWiki-produced bundles. Treat that file as a one-hop dependency whenever citation behavior changes.

### Validation matrix

When changing citation or adaptation behavior, verify at least these externally visible cases:

- initial pass on a valid bundle,
- below-floor bundle rejection,
- worktree citation rejection,
- unchanged source with no fidelity regression,
- bundle version override via `--version` if you touched version-selection logic.

### Minimal validation

- Focused: `cd /home/runner/work/foundry-assured/foundry-assured/apps/backend && uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend`
- Conditional broader check: re-run against another component only if your change touched shared citation parsing rather than backend-only content.

## Extension recipes

### Change the freshness trigger

Start with `_AREA` in `apps/backend/eval/wiki_freshness_test.py` and the `workflow_call.outputs.stale` contract in `.github/workflows/wiki-freshness.yml`.

Watch for:

- source paths that overlap `docs/wiki` and would self-trigger drift,
- new component names that need matching `foundry-helpdesk-*` bundle keys,
- preserving the invariant that stale status is emitted as output rather than failing the workflow.

Validate with `uv run python -m eval.wiki_freshness_test`.

### Change the OpenWiki-to-bundle adaptation

Start with `adapt()` in `apps/backend/app/knowledge/adapt_openwiki.py`, then inspect `validate_manifest()` and `docbundle_contract_test.py`.

Watch for:

- page ordering changes that could renumber `page-N.md`,
- front-matter/body handling that could leak YAML into retrieval,
- link-rewrite changes that could inflate fidelity scores,
- schema changes that require reader updates.

Validate with `uv run python -m eval.docbundle_contract_test`, then `uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend`.

### Change the acceptance threshold or citation parser

Start with `apps/backend/eval/assurance.yaml` and `apps/backend/app/knowledge/wiki_builder.py`.

Watch for:

- accidental divergence between locally generated bundles and externally generated ones,
- changes that improve one citation dialect while breaking another,
- false confidence from schema-valid bundles that still fail fidelity.

Validate first with `uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend`; broaden only if you changed shared parsing in `_fidelity_report()`.

## Scope boundaries

- This page stops at PR creation. Manual or separate workflow ingest into the selfwiki knowledge base remains documented in `docs/wiki/README.md` and source code under `apps/backend/app/knowledge/ingest_docbundles.py`.
- Do not hand-edit generated `docs/wiki/**` artifacts to test this path; the repository treats them as outputs of generation plus adaptation.
- Expensive end-to-end workflow runs are conditional. Most code changes in this area can be validated with the three focused Python module commands listed in the front matter.
