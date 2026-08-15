# ADR-016 — OpenWiki closes the freshness loop that ADR-012 only opened

- **Status:** Proposed — the decision below is contingent on the spike in *Exit criteria*;
  do not vendor or schedule anything before it passes
- **Date:** 2026-08-15
- **Extends:** [ADR-012](./ADR-012-reuse-upstream-deep-wiki-tooling.md) (generation engine +
  assurance layer stand; only the **freshness automation** changes)

## Context

ADR-012 made three calls. Two shipped, one did not.

| ADR-012 decided | As-built today |
|---|---|
| Vendor the upstream `microsoft/skills` deep-wiki plugin as the generator | ✅ `.github/skills/deep-wiki/`, plugin v2.0.0, pinned `5a6104bd`, MIT, 10 skills |
| Keep the assurance layer as the moat | ✅ bundle format, fidelity gate, freshness gate, KB ingest + ACL |
| Freshness → regen, **OpenWiki-style** | ❌ never implemented |

The third one shipped as [`wiki-regen.yml`](../../.github/workflows/wiki-regen.yml) — a
`workflow_dispatch` template whose regeneration step is a guarded `echo`:

```
echo "TODO(ADR-012): invoke a coding agent here with the prompt: ..."
echo "Guarded placeholder — wire your coding-agent action to make this real."
```

The pattern was documented, not built. The measurable consequence: the bundles are still at
**v0.3.0, generated 2026-07-02**, all four areas have drifted (`apps/backend` and
`apps/frontend` last changed 2026-08-15, `docs` and `infra` 2026-08-13), and
`deep-wiki tracks the code` has been **red on every pull request for six weeks** — PRs #105,
#125, #128, #130, #131, #133 all carry it. A gate that is always red is a gate nobody reads;
it has stopped carrying information.

Meanwhile [OpenWiki](https://github.com/langchain-ai/openwiki) (LangChain, MIT) — cited by name
in ADR-012 as the pattern to borrow — became a shipped tool rather than a reference:

- `npm install -g openwiki`; `openwiki --init`, `openwiki --update`, `-p/--print` for
  non-interactive one-shot runs.
- A copy-in CI workflow (`openwiki-update.yml`, plus GitLab and Bitbucket equivalents) that runs
  on a schedule, **diffs the commits since the last run**, updates only what changed, and
  **opens a pull request** — with snapshot-based no-op detection so an unchanged run produces no
  churn.
- Twelve model providers, Anthropic among them; credentials from CI secrets.
- Output as plain Markdown with YAML front matter, in **Open Knowledge Format (OKF) v0.1**,
  written to `openwiki/` in the repository.

That is precisely the loop this repository is missing, already built and maintained by someone
else. The ADR-012 lesson ("the generator and the freshness automation are commodities; our value
is the assurance layer") argues for consuming it rather than writing the guarded step ourselves.

## Decision

**Adopt OpenWiki as the freshness engine, behind an adapter, keeping the assurance layer
unchanged — contingent on the citation spike below.**

- **OpenWiki owns the loop**: schedule, git-diff-since-last-run, no-op detection, PR opening.
  Replaces the `wiki-regen.yml` placeholder rather than filling it in.
- **The assurance layer does not move**: the bundle format
  (`docs/wiki/<component>/<version>/{manifest.json, pages/page-N.md, llms.txt}`), the
  **fidelity gate** (`wiki_builder._fidelity_report`, floor `build.fidelity_min: 0.80` in
  `eval/assurance.yaml`), the freshness gate, and the Foundry KB ingest with per-document ACL
  stay exactly as they are. A bundle below the floor is still written for inspection and still
  refused for ingest.
- **An adapter bridges OKF → our bundle**, following the precedent that already exists:
  [`app/knowledge/adapt_deepwiki.py`](../../apps/backend/app/knowledge/adapt_deepwiki.py) does
  this today for the Copilot CLI deep-wiki output ("the second generation path"), recording the
  producer in the manifest's `model` field so paths stay distinguishable. OpenWiki becomes a
  third producer behind the same seam, not a second format.
- **The deep-wiki plugin stays vendored** as the generator for full regenerations and for the
  skills the loop does not cover (`wiki-llms-txt`, `wiki-qa`, `wiki-onboarding`, …). This ADR
  changes *what keeps the wiki current*, not *what writes it from scratch*.

## Exit criteria — the spike that decides this

**The blocking question is citations.** Our fidelity gate scores a bundle by the fraction of its
file citations that resolve to a real source file; the current bundles cite as pinned GitHub blob
URLs with line ranges:

```
https://github.com/ruinosus/foundry-assured/blob/3333d60d/apps/backend/app/main.py#L35
```

OpenWiki's documentation describes agent-written Markdown and validated Mermaid diagrams, but
**does not describe an automatic source-citation mechanism**. If its pages do not carry resolvable
file citations, the adapted bundle scores near zero and the fidelity gate refuses ingest —
correctly. That would not be a bug to work around; it would be this decision failing.

Run one area (`apps/backend`, the one that changed most) end to end and require:

1. `openwiki --update` produces pages carrying file citations, steered if necessary by
   `INSTRUCTIONS.md` (OpenWiki's user-authored scope-and-priorities file) demanding the blob-URL
   form.
2. The adapted bundle scores **≥ 0.80** on `_fidelity_report` — the same floor every other bundle
   answers to.
3. A second run with no source changes produces **no PR** (no-op detection holds).

If (1) or (2) fails, the fallback is the alternative already on the table: fill the
`wiki-regen.yml` guarded step with a coding-agent action driving the vendored `wiki-page-writer`,
which is known to emit the citation form the gate expects. **Do not lower `fidelity_min` to make
OpenWiki pass** — the floor is the reason the wiki is trustworthy at all.

## Consequences

**Good**

- The loop stops being ours to maintain. Diffing, scheduling, no-op detection and PR-opening are
  someone else's problem, on the same "don't reinvent" line as ADR-008/009/010/011 and ADR-012.
- The wiki can go back to being a signal. `deep-wiki tracks the code` becomes a gate that turns
  red on real drift instead of one that is red permanently.
- Provider-agnostic (twelve providers) — no lock-in to the model that happens to be wired today.

**Costs and risks, in the order they will bite**

- **`CLAUDE.md` collision — verify before the first run.** OpenWiki's code mode writes `AGENTS.md`
  and `CLAUDE.md` at the repository root as agent-readable pointers. This repository has a
  curated, hand-written `CLAUDE.md` that is the entry point for every session. An unscoped run
  would overwrite it. Confirm it can be disabled or redirected; if it cannot, that alone is
  disqualifying.
- **Telemetry is on by default.** It reports command type, outcome and provider — never files or
  credentials — but the data policy here is that nothing leaves the controlled environment
  without a reason. Set `OPENWIKI_TELEMETRY_DISABLED=1` (or `DO_NOT_TRACK=1`) in CI, not
  optionally.
- **A model credential in CI, and its spend.** Unavoidable in either path: the `wiki-regen.yml`
  placeholder is guarded behind exactly the same requirement. A daily schedule across four areas
  has a running cost — start on the manual trigger and only then schedule.
- **A third producer to keep honest.** `adapt_deepwiki.py` exists precisely because a second
  generator already grew its own reading of the format once; `eval/docbundle_contract_test.py`
  is the gate that caught it. A third producer needs the same discipline: record it in the
  manifest `model` field, and let the contract test hold the line.
- **OKF v0.1 is a young format.** A `0.1` spec will move. The adapter is the blast radius, which
  is the right place for it.

## Alternatives considered

- **Fill the `wiki-regen.yml` placeholder** with a coding-agent action driving the vendored
  `wiki-page-writer`. Smallest change, keeps citations and fidelity provably intact — but it
  means writing and maintaining the diff/no-op/PR loop that OpenWiki already ships. This is the
  fallback if the spike fails.
- **Keep it manual.** Rejected on evidence: it has been manual since 2026-07-02, and the result
  is six weeks of a permanently red gate.
- **Replace the deep-wiki plugin with OpenWiki entirely.** Rejected: it discards the vendored
  skills the loop does not cover and puts the citation-bearing generator — the one the fidelity
  gate depends on — at risk for no gain in the problem actually being solved.
- **Adopt DeepWiki (Cognition/Devin) as the source of truth.** Already rejected by ADR-012 and
  still right: hosted, not grounded in our KB, no ACL. It remains a complement for public human
  browsing.
