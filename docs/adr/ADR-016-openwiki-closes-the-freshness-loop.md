# ADR-016 — OpenWiki closes the freshness loop that ADR-012 only opened

- **Status:** Proposed — the spike ran (see *Spike log*): criterion 1 passes decisively,
  criterion 3 fails as written and needs the workflow change described there. The decision is
  ready for a call; nothing is scheduled until one is made.
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

- **OpenWiki owns the loop**: generation, git-diff-since-last-run, PR opening. Replaces the
  `wiki-regen.yml` placeholder rather than filling it in. It opens a pull request — it does not
  push to `main` — so human review stays in the path by construction.
- **The freshness check stops being a gate and becomes the trigger.** Today
  `wiki-freshness` fails a pull request when the wiki is older than its source. Once regeneration
  is automatic that gate is **green by construction** — it passes because a bot just touched the
  files, not because anyone verified anything, which is the same disease as a permanently red
  gate with the sign flipped. So it moves: `wiki_freshness_test` stays the deterministic answer to
  "did anything change?", and that answer decides whether `--update` runs, instead of decorating
  every unrelated PR with a red X. This also fixes the churn the spike measured (criterion 3):
  asking the agent only when something demonstrably changed sidesteps its self-assessed no-op.
- **Automation raises the value of the fidelity gate; it does not retire it.** Running in CI
  guarantees *freshness*, never *correctness*. Today a person generates the wiki and reads the
  result; afterwards a bot writes it daily and no one reads fifteen pages carefully. The
  `fidelity_min: 0.80` floor is then the only thing between an unattended writer and the
  knowledge base that answers users. Outsource the generator; never the verification.
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

The resulting shape, with each step owned by whoever should own it:

```
source changes
  → wiki_freshness_test detects drift        TRIGGER   — ours, deterministic
  → openwiki code --update                   GENERATOR — theirs, commodity
  → adapter → bundle                         FORMAT    — ours
  → fidelity >= 0.80                         GATE      — ours, the one that matters
  → pull request                             GATE      — human
  → Foundry KB ingest + ACL                  ours
```

**Adopt on `workflow_dispatch` first, schedule later.** Run it by hand once or twice, look at the
pull requests it opens, and measure the churn against a real review load before turning on the
daily cron. ADR-012 shipped a template that was never exercised; the difference now is that the
tool is real, so the trial can be too.

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

> **Outcome (2026-08-15):** (1) and (2) pass — 99.5% against the 0.80 floor. (3) does not: three
> unchanged runs still produced 15 → 2 → 1 file edits. The spike log records the measurement and
> the mitigation (drive `--update` from our own deterministic freshness gate instead of trusting
> the agent's self-assessed no-op).

## Consequences

**Good**

- The loop stops being ours to maintain. Diffing, scheduling, no-op detection and PR-opening are
  someone else's problem, on the same "don't reinvent" line as ADR-008/009/010/011 and ADR-012.
- The wiki can go back to being a signal. `deep-wiki tracks the code` becomes a gate that turns
  red on real drift instead of one that is red permanently.
- Provider-agnostic (twelve providers) — no lock-in to the model that happens to be wired today.

**Costs and risks, in the order they will bite**

- **~~`CLAUDE.md` collision~~ — cleared by the spike, see the log below.** It edits only a
  delimited managed block and fails safe. Left here struck through rather than deleted: the
  concern was raised from the published docs and answered by reading the tool, which is the
  point of running a spike before deciding.
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

## Spike log

### Phase A — read the tool, spend nothing (2026-08-15, `openwiki@0.3.3`)

Installed the CLI and inspected the shipped package rather than guessing from the README. Three
results, one of which corrects this ADR.

**1. The `CLAUDE.md` risk was overstated — cleared.** The code-mode agent prompt says, verbatim:

> Do not create or update repository /AGENTS.md or /CLAUDE.md files during normal code wiki runs.
> Keep generated wiki content under the repository /openwiki directory.
> Write generated files only under /openwiki. Do not modify source code, /AGENTS.md, /CLAUDE.md,
> or /openwiki/INSTRUCTIONS.md.

Where it does touch those files (setup), it writes inside a delimited region marked
`<!-- OPENWIKI:START -->` / `<!-- OPENWIKI:END -->`, and if the markers are damaged it refuses:
*"Repair or remove the markers and retry; the file was left unchanged."* It appends a managed
block and fails safe — it does not overwrite a curated file. The published README description
("writes AGENTS.md and CLAUDE.md at repo root") describes bootstrap, not steady state.

**2. The citation gap is real, and now has evidence instead of an absence of evidence.** The
concern was originally "the docs do not mention citations". Reading the packaged prompt and page
schema:

- OKF front matter carries `source: <Optional canonical URI for the underlying asset>` — **page
  level and optional**, not per-claim.
- The prompt does demand grounding: *"Ground every important claim in source files, tests,
  existing docs, or git evidence you have inspected"*, and pages must name *"owning entrypoints
  and symbols"*.
- But nothing instructs it to emit **file paths as links with line ranges**, and the link
  vocabulary throughout the prompt is about links *between wiki pages* for navigation.

So OpenWiki grounds *semantically* while our fidelity gate scores a *machine-checkable citation
form*. That is the whole question, unchanged in substance and sharper in shape: can
`openwiki/INSTRUCTIONS.md` steer the agent to emit the blob-URL form reliably enough to clear
0.80? Only a real run answers it.

**3. The loop is as advertised.** `shouldCheckUpdateNoop` plus snapshot tracking are in the
shipped code, both telemetry opt-outs (`OPENWIKI_TELEMETRY_DISABLED`, `DO_NOT_TRACK`) are
honoured, and the CLI exposes `--init` / `--update` / `--print` for non-interactive CI use.

### Phase B — the run that decides (2026-08-15)

Run against a throwaway `git worktree` of `main` at `0cb3b6d`, never the working tree. Scope
narrowed to `apps/backend` with `.openwikiignore`, and `openwiki/INSTRUCTIONS.md` carrying the
citation contract: the exact blob-URL form, the real HEAD SHA, at least five citations per
substantive page, never cite an uninspected file.

**Setup — Azure OpenAI works, and keyless works.** OpenWiki has no `azure` provider, but its
`openai-compatible` provider takes the Azure `/openai/v1` surface directly. Both auth modes were
measured against it: an AAD bearer token from `az account get-access-token` (keyless, matching
this repository's rule #2) and an API key passed as `Authorization: Bearer` — HTTP 200 on each.
No adapter needed.

**Model sizing is not a footnote.** The first run used `gpt-5-mini` (this project's own Foundry
deployment). It planned the wiki, then stalled in the critic loop without emitting a page. The
same run on `gpt-5.4` produced 15 pages. A small model is not a cheap version of this job.

**Criterion 1 — citations. PASSES, and beats the incumbent.** The `INSTRUCTIONS.md` steering
worked: 430 citations emitted in the `blob/<sha>/<path>#L<a>-L<b>` form. Scored with the real
gate (`wiki_builder._fidelity_report`, the same code that decides ingest):

| | OpenWiki (this spike) | deep-wiki v0.3.0 (in production) |
|---|---|---|
| Pages | 15 | 8 |
| Citations | 430 | 665 |
| Resolved | **99.5%** | 97.6% |
| Distinct files cited | **212** | 118 |
| Worktree citations | 0 | 0 |

99.5% against a floor of 0.80. The concern that opened this ADR — that OpenWiki grounds
semantically while our gate scores a machine-checkable form — is answered: the form is
steerable from `INSTRUCTIONS.md`, and the result is *more* faithful than what ships today.

*Metric footnote, not a gate:* `line_ranged` counted 0 despite every citation carrying a range.
`_CITE_RE` recognises `path:12-34` but not GitHub's `#L12-L34` anchor. The baseline scores 269
only because the older pages mix both dialects. Nothing gates on this field, but the repository
plainly has two citation dialects and the counter understands one.

**Criterion 3 — the no-op run. FAILS as written.** Three consecutive `--update` runs against an
unchanged `apps/backend`, comparing file hashes across all 18 documents:

| Run | Files changed | What the agent reported |
|---|---|---|
| 1 (`--init`) | 15 created | initial generation |
| 2 (`--update`) | 2 | fixed a broken trailing citation fragment and duplicated junk text — **defects from run 1** |
| 3 (`--update`) | 1 | revised `api-surface.md` route descriptions against six source files it re-inspected |

The **git-level** no-op detection works, and says so explicitly: *".last-update.json already
pointed at the current HEAD (…) so this was an accuracy audit rather than a history-diff update."*
It does not regenerate the wiki. But the accuracy audit still runs, and still finds something to
revise — 15 → 2 → 1, converging, yet not to zero within three runs.

On the daily schedule the shipped workflow uses, that opens a pull request most days carrying
agent-taste revisions rather than code-driven updates — the exact churn "no-op detection" was
supposed to prevent, and a reviewer cost paid against no code change.

**Mitigation, and it belongs in our workflow rather than in OpenWiki:** gate PR creation on an
actual source diff — run `--update` only when `wiki_freshness_test` reports drift, which is the
gate this repository already owns and which is deterministic. Trusting the agent to decide it has
nothing to do is the part that does not hold; asking it only when something demonstrably changed
sidesteps it entirely. (Spike artifact worth naming: `.openwikiignore` excluding everything but
one directory also restricted the agent's own `git` inspection — *"shell git inspection was
restricted by .openwikiignore"* — so real use would not narrow scope this way.)

**The `CLAUDE.md` behaviour, now measured rather than read.** `--init` *does* touch it — and the
diff is 8 lines, purely additive, inside the markers:

```markdown
<!-- OPENWIKI:START -->
## OpenWiki
See [AGENTS.md](AGENTS.md) for OpenWiki agent instructions.
<!-- OPENWIKI:END -->
```

Nothing curated was overwritten. `--init` also drops `AGENTS.md` and — worth knowing before it
surprises someone — `.github/workflows/openwiki-update.yml`, the recurrence workflow, straight
into the repository.

## Amendment (2026-08-15) — one wiki for the repository, not one per area

The loop shipped and produced a good backend bundle (11 pages, 98.8% fidelity, correctly scoped).
Running the **second** area exposed a mismatch the first one hid.

**OpenWiki keeps a single `openwiki/` per repository. Our bundles were per area.** With backend
already generated and committed, a `frontend` run would have found `openwiki/index.md` present —
so `--update` — and then updated a wiki *about the backend* while `.openwikiignore` scoped the
generator away from the very files that wiki describes. Every outcome of that is wrong, and the
backend bundle we had just approved was the thing at risk.

The first area worked only because it was an `--init` into an empty directory. That is not a
design; that is a starting condition.

**Decision: one wiki, one bundle — component `foundry-assured`, area `.`.** Per-area bundles were
inherited from `wiki_builder`, whose generator takes `--repo <area>` and genuinely produces one
per area. OpenWiki does not work that way, and bending it into that shape means fighting the tool
on every run. It also matches what the tool does best: an incremental `--update` against a wiki of
the whole repository, which is exactly the loop this ADR exists to consume.

What it costs, stated plainly:

- **Per-component ACL granularity goes away** for this path. The manifests already declare
  `groups: null` on both adapter paths (neither generator knows the repo's read groups), so
  nothing regresses today — but a future per-area ACL would need the split back.
- **The four per-area bundles are retired, not deleted.** They stay on disk and stay in the KB;
  they are simply no longer graded, because their areas no longer map to a generator that will
  ever refresh them. Grading them would report drift nobody can fix — a permanently red gate,
  which is the failure this ADR started from. `wiki_freshness_test` prints them as "not graded"
  rather than skipping them silently: unmeasured must look different from measured-and-fine.
- **Zero gradable bundles now reports drift**, not success. "0 bundles checked, all fresh" is the
  same disease in its purest form. It is also the useful answer — no wiki is precisely when
  regeneration should run.

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
