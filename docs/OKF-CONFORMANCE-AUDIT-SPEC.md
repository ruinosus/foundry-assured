---
type: Spec
title: OKF / OpenWiki conformance audit
description: Task spec for a coding agent to establish, from source, what this repo already does that conforms to OKF v0.2 and the OpenWiki conventions — and what it does not.
status: draft
audience: coding-agent
generated: { by: human:jefferson, at: 2026-09-02T00:00:00Z }
---

# OKF / OpenWiki conformance audit — task spec

## 0. How to use this document

You are auditing **this repository** (`ruinosus/foundry-assured`) against two external
things: the **Open Knowledge Format (OKF) v0.2** specification and the **OpenWiki**
conventions.

**Nothing in this document is authoritative.** §2 and §3 are an LLM summary of the
external specs, written in a chat session from a single read of each source. §4 is a set
of claims about this repo derived from its README and docs, not from its code. Both are
*expectations to test*, not ground truth. This repo's own
`docs/CASE-STUDY-LLM-WIKI-LOOP.md` is about what happens when you measure a system with
an LLM-authored ruler; this spec is that ruler until you verify it.

Rules for this task:

1. **Fetch the primary sources first (§1).** Do not begin the repo audit until the real
   spec text is on disk. Every conformance judgement must cite the fetched artifact, not
   §2 or §3.
2. **Audit only. Change nothing in this repo** unless explicitly asked in a later turn.
   The deliverable is a report, not a refactor.
3. **Cite a location for every finding** — `path:line` for repo code, and
   `<vendored-path>:<section or line>` for spec claims. A finding without a source
   location is not a finding. If you cannot locate evidence, write "not found" rather
   than inferring.
4. **Where §2/§3/§4 disagree with a primary source, the primary source wins — and the
   divergence is itself a finding.** Record it in the deliverable (§6 item 2). Do not
   silently correct it. The point is to know how far the summary drifted.
5. **Do not resolve open questions by guessing.** §7 lists decisions that are mine to
   make. Surface them; do not pick for me.

---

## 1. Step zero: get the primary sources on disk

Clone into a scratch directory outside the repo tree (or into a gitignored path), so
nothing here ends up committed:

```
mkdir -p /tmp/okf-audit && cd /tmp/okf-audit
git clone --depth 1 https://github.com/GoogleCloudPlatform/open-knowledge-format
git clone --depth 1 https://github.com/langchain-ai/openwiki
```

Record the **commit SHA and clone date of each** at the top of the findings document. A
"latest main" audit is not reproducible; a pinned one is. If either clone fails
(no network, proxy blocks the domain), stop and say so — do not fall back to §2/§3 and
present the result as verified.

Read, in this order:

| Artifact | Why it is the primary source |
|---|---|
| `open-knowledge-format/SPEC.md` | The normative text. §11 conformance is the pass/fail this audit turns on. |
| `open-knowledge-format/` sample bundles | Conformant bundles by the spec's own authors — the best available answer to "what does correct output actually look like". |
| `open-knowledge-format/README.md` | Version status, and whether v0.2 is still current as of your clone date. |
| `openwiki/openwiki/` | OpenWiki dogfoods itself: this is its own generated wiki, i.e. real OKF-shaped output from a real producer. Compare it against SPEC.md before trusting either. |
| `openwiki/` source (`src/`) | How the producer actually writes frontmatter, `index.md` and the log file — as code, not as a blog post claims. |
| `openwiki/README.md`, `docs/` | CLI surface and conventions. |

Two things to check specifically, because §2 and §3 of this document contradict each
other on the second:

- **What version does SPEC.md declare?** §2 asserts v0.2 and asserts the canonical repo
  moved out of `GoogleCloudPlatform/knowledge-catalog`. Confirm both from the fetched
  repos.
- **`log.md` or `logs.md`?** SPEC.md reserves one spelling; the LangChain blog post used
  the other. Determine what SPEC.md reserves and what OpenWiki's code actually emits. If
  they differ, that is a finding about OpenWiki, not about us.

**Do not run any code from the cloned repos.** Read them. In particular, do **not** run
`openwiki --init` or `--update` inside this repository: OpenWiki appends prompting to
`AGENTS.md` / `CLAUDE.md` (creating them if absent) and writes an `openwiki/` directory.
If a live trial is wanted later, it happens in a throwaway clone, as a separate decision.

Optional, only if the spec text leaves a question open: web-search for OKF errata,
issues, or a newer version. Prefer the repo's own issues and discussions over blog posts.
Do not cite a blog post where the spec says the same thing.

---

## 1b. Why this audit exists

This repo already builds LLM wikis from source and grounds an agent on them
(the `selfwiki` domain), and already has an assurance mechanism with measured CI gates.
OKF v0.2 independently standardized much of the same *metadata* surface — provenance,
trust, lifecycle. The question this audit answers is narrow and factual:

> Which parts of our wiki pipeline already emit or consume OKF-shaped structure, which
> parts are close but named differently, and which are absent?

That answer is a prerequisite for any decision about adopting OKF as our on-disk
format. **Do not make that decision here.**

---

## 2. Unverified summary: OKF v0.2

> **Read `open-knowledge-format/SPEC.md` before using anything below.** This section is a
> chat-session summary, useful as an expectation set and as a reading guide — it tells you
> which parts of the spec matter for this audit. It is not evidence. Every item here is a
> claim to check against the fetched text, and divergences go in the findings.

### 2.1 Provenance and status of the standard

- OKF is an open, vendor-neutral specification from Google Cloud (Data Cloud team;
  authors Sam McVeety and Amir Hormati). v0.1 was announced 2026-06-12.
- **The current version is v0.2.** It supersedes v0.1.
- **The canonical repo moved.** It is now `GoogleCloudPlatform/open-knowledge-format`.
  The `okf/` directory inside `GoogleCloudPlatform/knowledge-catalog` is a frozen,
  unmaintained snapshot; its own README tells readers to stop using it. If anything in
  this repo links to the `knowledge-catalog` path, that is a finding.

### 2.2 The model

- **Bundle** — a directory tree of markdown files; the unit of distribution. May be a
  git repo, a tarball, or a subdirectory of a larger repo.
- **Concept** — one markdown file. Its **Concept ID is its path within the bundle with
  `.md` removed**.
- **Frontmatter** — YAML block delimited by `---`. **Body** — everything after it.
- **Links** — ordinary markdown links between concepts form a graph richer than the
  filesystem hierarchy. Bundle-relative links beginning with `/` are the recommended
  form. Consumers must tolerate broken links (they may be not-yet-written knowledge).

### 2.3 Reserved filenames

`index.md` and `log.md` have defined meaning at **any** level of the tree and MUST NOT
be used as concept documents. Note the singular: the spec says `log.md`. (The LangChain
OpenWiki blog post writes `logs.md`; the spec is authoritative.)

- `index.md` — directory listing for progressive disclosure. **Contains no
  frontmatter**, with exactly one exception: the bundle-root `index.md` may carry
  `okf_version: "0.2"`. Body is one or more `#` sections of
  `* [Title](url) - description` entries, where the description should be the linked
  concept's frontmatter `description`.
- `log.md` — chronological update history, newest first, date headings in ISO
  `YYYY-MM-DD` form. The leading bold word (`**Update**`, `**Creation**`,
  `**Deprecation**`) is convention, not requirement.

### 2.4 Frontmatter fields

Required:

| Field | Notes |
|---|---|
| `type` | Non-empty string. The **only** always-required key. Not centrally registered; consumers must tolerate unknown values. |

Recommended: `title`, `description` (one sentence; feeds index generators and search
snippets), `resource` (canonical URI of the underlying asset; absent for abstract
concepts), `tags` (list of short strings).

Optional families (v0.2), all of which may be absent — **absence carries meaning but is
never grounds for rejection**:

| Family | Fields |
|---|---|
| Provenance | `sources[]` with `resource` (required within an entry), `id`, `title`, and credibility signals `author`, `usage_count`, `last_modified`; plus a `usage_window: { from, to }` sibling framing all `usage_count` values |
| Trust | `generated: { by, at }` (`by` required); `verified: [{ by, at }]` |
| Lifecycle | `status: draft \| stable \| deprecated` (absent ⇒ `stable`); `stale_after: <absolute ISO instant>` |
| Computation | `runtime`, `parameters`, `computation`, `executor`, `attester` — only on `type: Attested Computation` |

All timestamps are ISO 8601 with an explicit UTC offset. Producers may add arbitrary
extra keys; consumers should preserve unknown keys on round-trip.

### 2.5 Rules that are easy to get wrong

- **`generated` vs `verified` are deliberately distinct.** Who wrote a concept need not
  be who confirmed it. Content can change without re-confirmation; facts can be
  re-confirmed without regeneration. `verified` is a *list* of events, but a single
  bare `{ by, at }` mapping is legal and consumers must treat it as a one-element list.
- **Actor convention** for `generated.by` and `verified[].by`: `<producer>/<version>`
  for agents and tools, `human:<id>` for people, `process:<id>` for automated
  processes. Trust classification keys off the `human:` prefix, so producers must use
  it for hand-authored or human-confirmed content.
- **Trust tiers are derived, never stored**: no `verified` ⇒ unverified; `verified` by
  non-`human:` actors only ⇒ machine-confirmed; any `human:<id>` ⇒ human-reviewed.
- **Trust tiers are advisory signals and explicitly NOT access control.** This matters
  for us — see §7.3.
- **No credibility score is stored.** Only objective per-source signals; the consumer
  infers.
- **Per-claim attribution uses markdown footnotes keyed to a `sources[].id`**, not a
  body citations list and not a positional index — because agents constantly rewrite
  these files and a positional reference misattributes silently after any reorder.
- **`stale_after` is an absolute instant, not a relative TTL**, so staleness is a plain
  comparison against `now`.

### 2.6 Breaking changes from v0.1

- `timestamp` is superseded by `generated.at` (consumers may fall back to the legacy
  key when `generated` is absent).
- A body `# Citations` list is superseded by frontmatter `sources` (consumers should
  read `sources`, may still parse legacy `# Citations`).

Everything else — bundle structure, reserved filenames, required `type`, recommended
`title`/`description`/`resource`/`tags`, cross-linking, index files, log files,
permissive conformance — carries forward unchanged.

### 2.7 Conformance test (spec §11) — use this verbatim as the audit's pass/fail

A bundle conforms to OKF v0.2 if:

1. Every non-reserved `.md` file in the tree has a parseable YAML frontmatter block.
2. Every frontmatter block has a non-empty `type`.
3. Every reserved filename (`index.md`, `log.md`) follows its defined structure when
   present.

And consumers MUST NOT reject a bundle for: missing optional frontmatter fields;
unknown `type` values; unknown additional frontmatter keys; broken cross-links; missing
`index.md` files.

### 2.8 Attested Computation (background; likely out of scope here)

A `type: Attested Computation` concept carries the *sanctioned way to compute a value*
so a consumer can confirm the agent ran the blessed computation rather than improvising.
`executor.resource` names run instructions; `executor.receipt` declares the fields a run
must return; `attester.resource` names deterministic, no-LLM code that reads the receipt
and returns a verdict, consumer-side. The agent may only supply *values* for declared
`parameters` — never author or edit the computation. Comparison happens on the expanded,
compiled artifact the receipt carries (`executed_sql`, `compiled_sql`), so a rewritten
query or swapped computation file fails the check.

Distinction to keep straight: `verified` confirms the *definition* still matches policy
(doc-level, slow, stored in the bundle); attestation confirms a single *run* produced the
value the sanctioned way (per-call, runtime, **not** stored in the bundle).

Include this in the audit only to answer §5 task 7.

---

## 3. Unverified summary: OpenWiki

> **Read the cloned `openwiki/` repo before using anything below.** Same standing as §2:
> an expectation set, not evidence. The blog-derived claims here are the ones most likely
> to have drifted from the code.

- OpenWiki is LangChain's open-source CLI that generates and maintains a markdown wiki
  for a codebase, wires it into coding agents, and keeps it current as code changes.
  npm package `openwiki`; Node 22+; TypeScript/pnpm; engine is a Deep Agents
  documentation agent.
- Commands: `openwiki --init`, `openwiki --update`, `openwiki` (interactive),
  `-p/--print` for one-shot. It writes to `openwiki/` when no wiki exists and refreshes
  that directory when it does. There is also a `openwiki personal --init` mode building
  a local wiki from connectors (git, MCP, Gmail, Notion, web search, HN, X).
- It appends prompting to `AGENTS.md` and/or `CLAUDE.md` so coding agents consult the
  wiki, creating those files if absent.
- A shipped GitHub Action opens a documentation-update PR daily.
- **0.2 adopted OKF.** Generated wikis carry YAML front matter (title, description,
  tags, categories, resource URLs).

Two implementation ideas from OpenWiki 0.2 worth evaluating independently of adopting
the tool:

1. `index.md` generated **deterministically** by extracting the `description` field from
   sibling concepts' frontmatter — no LLM pass for index construction.
2. `log.md` generated by **prompting** at the end of a run, so a reviewer reads the
   changelog instead of re-reading the whole wiki after every update.

The stated payoff of structured metadata is deterministic filtering on tags/categories
before falling back to open-ended agentic search, which is slower and more expensive for
simple lookups.

**What OpenWiki does not do:** there is no verification pass and no measured gate. That
is this repo's differentiator, per §4.

---

## 4. Claims about this repo — CONFIRM OR REFUTE

Each of these came from `README.md` or `docs/CASE-STUDY-LLM-WIKI-LOOP.md`. None was read
from code. Confirm each against source and record `path:line`.

**C1.** There are two wiki-generation paths: a Foundry pipeline (`wiki_builder.py`,
`gpt-5-mini` per README) and Microsoft Agent Skills under
`apps/backend/app/knowledge/skills/{wiki-architect,wiki-page-writer}`.

**C2. Path discrepancy — resolve this first.** `README.md` points the generator at
`apps/backend/app/knowledge/wiki_builder.py`, while
`docs/CASE-STUDY-LLM-WIKI-LOOP.md` points at
`apps/backend/app/modules/knowledge/internal/wiki_builder.py`. Determine which path is
real on `main`, and report the stale reference as a defect.

**C3.** The `selfwiki` domain grounds a cited Q&A agent on a deep-wiki generated from
this repo's own source, ingested into a Foundry IQ knowledge base.

**C4.** The Build pillar of the assurance mechanism is "every wiki claim cites a real
source file", enforced by a fidelity gate in `wiki_builder`, with thresholds in
`apps/backend/eval/assurance.yaml`.

**C5.** Generated pages cite source with **line ranges** (`src/<File>.cs:95-123`).
Establish the actual citation format the generator emits, byte-exactly.

**C6.** The case study's own frontmatter is `type: explanation`, `title`, `description`,
`audience: evaluator`, `status: stable`, `updated: 2026-06-27`. If so, that file is
already OKF-conformant under §2.7 (non-empty `type`), with `updated` being the legacy
analogue of `generated.at` and `audience` a legal producer-defined key.

**C7.** The consume side is Foundry IQ's `AzureAISearchContextProvider`, with the
answering discipline in `COCKPIT_INSTRUCTIONS`, and no consume-side skill.

---

## 5. The audit tasks

Work through these in order. Record evidence as you go.

1. **Locate every wiki artifact directory in the repo.** Generated wiki output, sample
   wikis, committed fixtures. For each, report: path, file count, and whether it is
   committed or gitignored.

2. **Frontmatter inventory.** Across all markdown under `docs/` and any wiki output
   directory, produce a table: file → has frontmatter (y/n) → keys present. Then
   summarize: how many files would pass §2.7 rules 1 and 2 today, unchanged.

3. **Key-name mapping.** For every frontmatter key found anywhere in the repo, classify
   it as: (a) an OKF v0.2 key used correctly; (b) a repo-specific key that is a *near
   miss* for an OKF key (e.g. `updated` vs `generated.at`); (c) a producer-defined key
   with no OKF analogue, which is legal and needs no change. Do not propose renames yet.

4. **Reserved-filename check.** Find every `index.md`, `log.md`, and `logs.md` in the
   repo. For each: does it carry frontmatter (illegal except at bundle root)? Does its
   body match the structure in §2.3? Is any of them being used as a concept document?

5. **Generator behavior.** Read the real `wiki_builder` (path per C2) and the two
   Agent Skills. Answer from code, not from docs:
   - Does the generator emit frontmatter at all? Which keys, with what values?
   - Does it generate `index.md`? Deterministically from `description`, or via the LLM?
   - Does it generate any changelog/log file?
   - How does it record *who generated* a page and *with which model*? Is there
     anything shaped like the actor convention (§2.5)?
   - How does it record the verifier pass? Is generation distinguishable from
     verification in the output artifact, or only in the run logs?
   - What exactly does the fidelity gate assert, and where does it read its threshold?

6. **Consumer behavior.** Read the ingest path and the retrieval configuration.
   - Are frontmatter fields extracted into indexed/filterable fields in Azure AI Search,
     or is the whole file chunked as text?
   - Is there any deterministic pre-filter before agentic retrieval today?
   - Would a consumer in this repo reject a document for a missing optional field,
     an unknown `type`, or a broken cross-link? (Any "yes" is a v0.2 conformance
     violation on the consume side — §2.7.)

7. **Attested Computation applicability.** State in three sentences whether the
   assurance mechanism's eval gates map onto the `executor` / `receipt` / `attester`
   interface, or whether the analogy breaks down. Evidence from
   `apps/backend/eval/` only. No recommendation.

8. **Stale external references.** Grep the repo for links to
   `knowledge-catalog/.../okf` or any OKF v0.1 assumption, and for `logs.md` where
   `log.md` is meant.

---

## 6. Deliverable

Write `docs/OKF-CONFORMANCE-FINDINGS.md` with, in this order:

0. **Pinned sources** — for each cloned repo: URL, commit SHA, clone date. Plus the OKF
   version SPEC.md declares. Everything below is only valid against these.
1. **Verdict paragraph** — one paragraph, no hedging: is any part of this repo emitting
   OKF-conformant output today, yes or no, and under which of the spec's conformance
   rules it passes or fails.
2. **Summary-drift table** — every place where §2, §3, or §4 of this spec diverged from
   the primary sources, with what the primary actually says. If nothing diverged, say so
   explicitly; a silent absence is indistinguishable from not having checked.
3. **Claims table** — C1–C7, each marked `confirmed` / `refuted` / `partially
   confirmed`, with `path:line` evidence and a one-line note.
4. **Conformance table** — the spec's conformance rules plus the consume-side MUST NOTs,
   each pass/fail, per wiki artifact directory found in task 1, citing SPEC.md sections.
5. **Gap list** — what is absent, ordered by how much work it looks like, with no
   recommendation attached. Facts only.
6. **Near-miss list** — repo keys and behaviors that already do the OKF job under a
   different name, with the mapping.
7. **Defects found incidentally** — e.g. the C2 path discrepancy. These are real bugs
   regardless of what we decide about OKF.
8. **Open questions** — anything you could not settle from source, phrased as a question
   with the specific file you would need to see or the command you would need to run.

Keep it to what you verified. An honest "not found" beats a plausible reconstruction —
that is the entire lesson of `docs/CASE-STUDY-LLM-WIKI-LOOP.md`, and this audit will be
read by the same standard it argues for.

---

## 7. Open questions — mine to decide, not yours

State these in the findings as still-open. Do not answer them.

**7.1 Format vs. pipeline.** Adopting OKF on disk is separable from adopting OpenWiki as
a generator. The audit should make clear which of our current capabilities depend on
which.

**7.2 `log.md` cost.** Whether a per-run changelog is worth the prompt surface, given
that git history already carries the diff.

**7.3 Access control stays out of frontmatter.** OKF explicitly scopes trust tiers as
advisory and not access control (§2.5). Our access-control pillar enforces pre-model and
follows the source. Nothing in this audit should propose moving that decision into
document frontmatter. If you find any code path where a frontmatter field influences an
access decision, flag it as a security finding, not as an OKF opportunity.

---

## 8. Sources

These are the URLs the §2/§3 summary was written from, on 2026-09-02, in a chat session.
They are listed for traceability, not as citations you may reuse: the first two rows are
now cloned locally per §1 and the clone is what you cite. The rest are secondary and
should only appear in the findings where the primary sources are silent.

| What | Where |
|---|---|
| OKF v0.2 specification (canonical) | `github.com/GoogleCloudPlatform/open-knowledge-format` → `SPEC.md` |
| OKF announcement, v0.1 | `cloud.google.com/blog/products/data-analytics/how-the-open-knowledge-format-can-improve-data-sharing` |
| Frozen v0.1 snapshot + "moved" notice | `github.com/GoogleCloudPlatform/knowledge-catalog` → `okf/README.md` |
| OpenWiki 0.2 / OKF adoption | `langchain.com/blog/openwiki-0-2-adds-okf-support` |
| OpenWiki repo and CLI reference | `github.com/langchain-ai/openwiki` |
| OpenWiki docs | `docs.langchain.com/oss/openwiki/overview` |
| Karpathy's LLM Wiki gist (the pattern OKF formalizes) | `gist.github.com/karpathy/442a6bf555914893e9891c11519de94f` |
| Third-party OKF ecosystem tooling (context only) | `pypi.org/project/google-okf`, `github.com/eli-l/okf-builder` |

Repo-internal material behind §4: `README.md`, `docs/CASE-STUDY-LLM-WIKI-LOOP.md`.