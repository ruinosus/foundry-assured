# Wiki automation decision

Consult this page when a proposed change questions the overall shape of the self-wiki maintenance system rather than a single file. The operational details live in the wiki refresh loop; this page explains **why** the loop is structured that way.

## Decision summary

`docs/adr/ADR-016-openwiki-closes-the-freshness-loop.md` extends `docs/adr/ADR-012-reuse-upstream-deep-wiki-tooling.md`.

ADR-012 already made two durable choices:

- reuse upstream tooling for self-wiki generation,
- keep the repository's own assurance layer: bundle format, fidelity checks, freshness checks, and ingest behavior.

What ADR-012 did **not** fully implement was the final freshness-to-regeneration loop. The repository had a `wiki-regen.yml` template with a guarded `echo`, while the `wiki-freshness` signal was red on every PR. ADR-016 replaces that incomplete loop with a concrete split of responsibilities:

- **Repository-owned:** deterministic drift detection, OKF-to-docbundle adaptation, fidelity gate, and human PR review.
- **OpenWiki-owned:** diff-aware wiki regeneration in `openwiki/`.

That relationship is realized by the wiki refresh loop.

## Why freshness became a trigger instead of a PR gate

ADR-016 argues that both extremes are misleading:

- an always-red check stops carrying information,
- an auto-regenerated always-green check would also stop carrying information.

So `wiki-freshness.yml` changed role. It still computes the same answer using `eval/wiki_freshness_test.py`, but the answer is now consumed by `wiki-regen.yml` as `stale=true|false` instead of decorating unrelated pull requests.

This is the most important architectural invariant to preserve if you revisit the workflow design. If you reintroduce PR gating, you need a new reason that survives the ADR's critique, not just a preference for visible checks.

## Why the adapter remains local

OpenWiki writes OKF Markdown to `openwiki/`, but the rest of the repository already depends on a different artifact contract:

- `docs/wiki/<component>/<version>/manifest.json`
- `docs/wiki/<component>/<version>/pages/page-N.md`
- `docs/wiki/<component>/<version>/llms.txt`

That bundle is what ingest, ACL handling, and historical selfwiki tooling understand. ADR-016 therefore keeps adaptation local through `apps/backend/app/knowledge/adapt_openwiki.py` rather than asking every downstream consumer to learn raw OpenWiki output.

This page intentionally links back to the wiki refresh loop because the adapter is not only format translation; it also carries trust decisions about page ordering, front-matter stripping, internal-link flattening, and manifest provenance.

## Why the fidelity gate matters more after automation

Automation solves freshness, not correctness. ADR-016 explicitly says the fidelity gate becomes **more** valuable once a bot writes wiki content unattended.

That principle is implemented by keeping externally generated bundles on the same scoring path as locally generated ones:

- threshold source: `apps/backend/eval/assurance.yaml` `build.fidelity_min`,
- scoring logic: `apps/backend/app/knowledge/wiki_builder.py` `_fidelity_report()`,
- external-bundle entrypoint: `apps/backend/eval/wiki_fidelity_test.py`.

If you remove or weaken that shared gate, you are not just simplifying code; you are changing the trust model ADR-016 adopted.

## Decision boundaries for future changes

Use this checklist before altering the design:

1. **Are you changing a commodity concern or a trust boundary?**
   - Commodity: generation engine details, provider wiring, workflow ergonomics.
   - Trust boundary: drift detection semantics, bundle contract, fidelity floor, human review.
2. **Does the change preserve one acceptance path for all wiki producers?**
   The repo currently avoids separate correctness definitions for `wiki_builder`, `adapt_deepwiki`, and `adapt_openwiki` outputs.
3. **Does the change create review noise?**
   ADR-016 is explicitly cautious about scheduled automation because repeated unchanged runs still produced small edits.

## Narrow validation

- Architectural reasoning check: read ADR-016 and ADR-012 together before editing workflows or acceptance gates.
- Source-backed sanity check: `cd /home/runner/work/foundry-assured/foundry-assured && git log --oneline -n 5 -- docs/adr .github/workflows apps/backend/app/knowledge apps/backend/eval`
- Behavior checks: follow the focused commands listed on the wiki refresh loop.

## Scope boundaries

- This page summarizes ADR-backed intent; it is not the canonical home for command details or environment variables.
- It also does not duplicate the broader `docs/wiki/README.md` ingest instructions, because ADR-016 changed pre-ingest automation rather than ingest semantics.
