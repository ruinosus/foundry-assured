# OpenWiki quickstart

This repository did not previously have an `openwiki/` knowledge base checked in. This run creates the minimal OpenWiki entrypoint and documents the repository area that changed since the last inspected commits: the **self-wiki freshness loop** that now uses OpenWiki as the regeneration engine behind the repository's existing bundle and assurance layer.

Start here when you need to change any of the following:

- the GitHub Actions that decide **when** generated wiki content is stale,
- the adapter that converts `openwiki/**/*.md` OKF pages into `docs/wiki/<component>/<version>` bundles,
- the fidelity gate that decides whether an externally generated bundle may reach the knowledge base,
- or the ADR-backed rationale for why freshness moved from a visible PR gate to an internal trigger.

## What this wiki currently covers

- Wiki refresh loop is the canonical operational page for the new automation path: drift detection, OpenWiki generation, bundle adaptation, fidelity gating, and PR creation.
- Wiki automation decision captures the architectural rationale from ADR-016 and how it extends ADR-012 without replacing the existing assurance layer.

## Task routing

| Change area or user intent | Relevant wiki page | Exact source entry points | Important symbols or types | Focused tests | Minimal validation command |
| --- | --- | --- | --- | --- | --- |
| Change when wiki drift is detected or how drift is surfaced to callers | Wiki refresh loop | `.github/workflows/wiki-freshness.yml`, `apps/backend/eval/wiki_freshness_test.py` | `freshness` job, `stale` workflow output, `_AREA`, `_latest_commit_iso()` | `apps/backend/eval/wiki_freshness_test.py` | `cd /home/runner/work/foundry-assured/foundry-assured/apps/backend && uv run python -m eval.wiki_freshness_test` |
| Change the regeneration workflow, OpenWiki invocation, or PR-opening behavior | Wiki refresh loop | `.github/workflows/wiki-regen.yml` | `drift` job, `regen` job, `OPENWIKI_PROVIDER`, `OPENWIKI_MODEL` | workflow YAML review; pair with `wiki_fidelity_test.py` when output shape changes | `cd /home/runner/work/foundry-assured/foundry-assured && git diff -- .github/workflows/wiki-regen.yml` |
| Change how OpenWiki output becomes an ingest bundle | Wiki refresh loop | `apps/backend/app/knowledge/adapt_openwiki.py`, `apps/backend/app/knowledge/docbundle_schema.py` | `adapt()`, `_ordered_pages()`, `_flatten_internal_links()`, `validate_manifest()` | `apps/backend/eval/docbundle_contract_test.py` | `cd /home/runner/work/foundry-assured/foundry-assured/apps/backend && uv run python -m eval.docbundle_contract_test` |
| Change the fidelity floor or how external bundles are accepted/rejected | Wiki refresh loop | `apps/backend/eval/wiki_fidelity_test.py`, `apps/backend/app/knowledge/wiki_builder.py`, `apps/backend/eval/assurance.yaml` | `_fidelity_report()`, `_fidelity_floor()`, `gather_source()` | `apps/backend/eval/wiki_fidelity_test.py` | `cd /home/runner/work/foundry-assured/foundry-assured/apps/backend && uv run python -m eval.wiki_fidelity_test --component foundry-helpdesk-backend` |
| Understand why the repo adopted OpenWiki for freshness but kept its own bundle and assurance seams | Wiki automation decision | `docs/adr/ADR-016-openwiki-closes-the-freshness-loop.md`, `docs/adr/ADR-012-reuse-upstream-deep-wiki-tooling.md` | ADR-012, ADR-016 | ADR text plus source pages above | `cd /home/runner/work/foundry-assured/foundry-assured && git log --oneline -n 5 -- docs/adr .github/workflows apps/backend/app/knowledge apps/backend/eval` |

## How the documented workflow fits the repo

The generated self-wiki is not consumed directly from `openwiki/`. OpenWiki now writes OKF Markdown into `openwiki/`, then `adapt_openwiki.py` rewrites that output into the repository's established `docs/wiki` bundle format, and the wiki automation decision explains why the repository keeps that seam: ingest, ACL semantics, and assurance gates already depend on the bundle contract.

The automation path also depends on the same fidelity math the original Foundry-based generator uses. `wiki_fidelity_test.py` intentionally reuses `wiki_builder._fidelity_report()` and the `build.fidelity_min` threshold instead of creating a second acceptance rule for externally generated output.

## Change guidance

- **When to start with the workflow page:** any edit under `.github/workflows/wiki-freshness.yml`, `.github/workflows/wiki-regen.yml`, `apps/backend/app/knowledge/adapt_openwiki.py`, or `apps/backend/eval/wiki_fidelity_test.py`.
- **When to start with the architecture page:** when a change questions whether freshness should still be a trigger instead of a PR gate, whether OpenWiki should remain the generator, or whether the adapter/fidelity seam should be removed.
- **Scope boundary:** this wiki does not yet attempt full repository coverage. It documents the changed, high-centrality maintenance path introduced by the latest commits. Other repository domains remain in source docs under `README.md`, `docs/`, and `apps/backend/eval/README.md` until later OpenWiki updates expand coverage.

## Backlog

- Broader repository coverage is still absent because no prior `openwiki/` tree existed in the repository, and this update is scoped to the evidence-backed freshness-loop changes introduced by `f7dc471..f8cd8c2`.
