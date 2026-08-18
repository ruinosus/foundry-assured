---
title: 'Design: citation resolvability as a product — connect a repo, measure its docs, then index them'
description: Turn the wiki pipeline (generate → gate → ingest) into a product a user can point at their own GitHub repository. The entry product is not generation, it is the MEASUREMENT — a deterministic, auditable score of how many file citations in existing documentation still resolve. Grounded in a survey of prior art and in what this repo's own gate has been measured to catch and to miss.
type: design
audience: contributor
status: draft
updated: 2026-08-16
---

# Citation resolvability as a product

## The idea, in one line

A user connects their GitHub account, points at a repository, and gets back a number:
**how much of your documentation still refers to files that exist**. If they have no
documentation, we generate it. If they like the result, we index it and give them an agent
that answers from it, with citations and per-document access control.

## Why the measurement comes first, not the generation

"Chat with your repository" is a crowded field and needs a model to run. The measurement
needs no model at all — it is string resolution against a file tree — and it answers a
question nobody is answering:

> *Your documentation says it describes this system. How much of it still points at
> something real?*

It is also the cheapest thing we can ship, because **the implementation already exists and
has been exercised in anger**: `wiki_builder._fidelity_report` takes `pages` (any list of
`{"content": str}`) and `files` (a `path → text` map of the repo) and returns a score. It
does not know or care who wrote the pages. That indifference is what makes it a product
rather than an internal gate.

Measured cost in this repository: **6.2s** to read 509 source files, then **0.01–0.03s per
bundle**. No tokens.

## Prior art — surveyed before writing this

Three places to look, three different answers.

**Academia has a mature field, measuring something else.** *Code-Comment Inconsistency
Detection* is well developed (MCCL reports F1 82.6%; C4RLLaMA both detects and rectifies).
The unit of analysis is a **comment against its function**, judged by a trained model. Nobody
there measures prose documentation against a whole repository.

**Industry sells drift detection against a generator.** Mintlify, GitBook, Augment and Dosu
compare published docs to the artifact they were generated from — an OpenAPI spec, a source
file — and use an LLM to judge. The output is a list of issues, not an auditable number.

**Open source is close to empty.** Searching GitHub for "documentation drift", "docs sync
code", "documentation coverage" returns prototypes: the largest is 6 stars, the `drift` tool
linked from driftdev.sh has 4. Hackathon projects and personal VS Code extensions.

So the space is not crowded. But the honest reading is not "we are ahead" — see the next
section.

## What our gate actually measures, and what it does not

**It measures resolvability of citations, not truth of claims.** A page can cite
`infra/resources.bicep`, which certainly exists, and describe it as it was a generation ago.

This is not hypothetical, and it is not a small effect. On 2026-08-16 the bundle in
circulation scored **94.3%** and simultaneously said:

- "Next.js **15** + CopilotKit v2" — it is 16
- "ADRs 001–**011**" — they run to 018
- "**4** domains" — there are 5
- 76 mentions of a domain named `cockpit`, renamed to `techdocs` 96 minutes before that
  bundle was generated

Every one of those citations resolved. Three retired bundles scored 81.5%, 96.2% and 96.2%
and were stale in exactly the same way.

**Therefore: "fidelity" is a generous name and this spec stops using it.** The metric is
**citation resolvability**. Naming it accurately is not pedantry — a product that promises
fidelity and delivers resolvability will be caught by the first customer whose docs are
well-cited and wrong.

### The consequence for the product

Resolvability is a **floor**, and floors are useful precisely because they are cheap and
total: every citation, every push, no sampling, no model, no judgement to argue with. It
catches the failure mode that actually dominates — a refactor moved the files — and it
catches it for free.

Semantic staleness is a **ceiling**, and needs a judge. The academic work shows an LLM judge
is viable at this task. Nothing surveyed above combines the two, and that combination is the
defensible product:

| Layer | Question | Cost | Runs |
|---|---|---|---|
| Resolvability (have it) | does the cited path exist? | ~0 | every push |
| Freshness (have it) | is the doc older than the code it describes? | ~0 | every push |
| Semantic (do not have it) | is the sentence still true? | tokens | on demand |

## What already exists

| Capability | Where | State |
|---|---|---|
| Connect GitHub as the user | `dna-cloud` — GitHub App "DNA Cloud Connect", user-to-server token (~8h) with refresh (~6mo), encrypted per Entra `oid` | works |
| Read the repo | falls out of the token above | — |
| Measure resolvability | `wiki_builder._fidelity_report` | works, origin-agnostic |
| Measure freshness | `eval/wiki_freshness_test` | works |
| Guard the shelf | `eval/wiki_shelf_test` — model + resolvability + freshness | works |
| Generate a wiki | `openwiki` + `adapt_openwiki` | works |
| Ingest with per-document ACL | `ingest_docbundles` + Azure AI Search | works |
| Isolate per customer | deployment-mode seam + `TenantConfigProvider` | works |

The gap is **glue**, not invention. The one genuinely new piece is the ingestion trigger,
which today is a person remembering to run a command — and the measured result of relying on
that is the `cockpit` incident above.

## Design

### Flow

```
connect GitHub (dna-cloud App, user token)
        │
        ▼
point at a repository
        │
        ├── has documentation ──► MEASURE ──► report: N of M citations resolve
        │                                     │
        │                                     └─► offer: index it
        │
        └── has none ──────────► GENERATE (openwiki) ──► GATE ──► index
                                                          │
                                                     below floor
                                                          └─► do not index; show why
```

### The measurement is the entry point

Input: a repository and a docs path. Output, per document and in aggregate:

- citations found, citations resolved, score
- the unresolved ones, listed — this is the actionable part, not the percentage
- freshness: newest doc timestamp vs newest commit touching the described area

### "Not measurable" is a first-class result

Human-written documentation frequently describes without citing paths. Such a corpus scores
0% under `_CITE_RE`, and reporting that as "0% fidelity" would tell a customer their docs are
worthless when they merely have a different style.

**The product must distinguish `0 citations found` from `0 citations resolved`.** The first
is *not measurable by this method*; the second is *measurably broken*. Collapsing them is the
fastest way to lose trust, and the current gate does not make this distinction — it is new
work.

### Ingestion closes the loop

Per the proposal in `scratchpad/wiki-ingest-proposta.yml`: ingestion runs automatically after
approval, and **the gate runs immediately before the write, not only at generation**. Any
distance between verifying and writing is room for the two to diverge — which is precisely
what put a stale bundle in the knowledge base.

## Risks and open questions

**Cost per customer.** AI Search Basic is ~US$73/month *per service* (measured, `eastus2`
retail). One index per customer does not close. The path is a shared index with per-tenant
ACL — the mechanism the `techdocs` domain exists to demonstrate. The showcase's thesis
becomes a product requirement.

**Someone's private repository in our index.** This stops being a technical detail and
becomes a contract: where the data lives, who can reach it, how it is deleted. The
`dedicated` deployment mode (a stamp in the customer's own subscription) exists for customers
who will not accept multi-tenant, and is the honest answer for them.

**Scale.** `gather_source` reads the whole repository into memory with a 16k-char cap per
file. Fine for 509 files; a customer monorepo breaks it. Needs streaming or sampling before
this meets a real repository.

**Citation-format coupling.** `_CITE_RE` recognises repo-relative paths and GitHub blob URLs
because those are the two shapes our own generators emit. A customer's docs may use neither.
The parser becomes a supported surface, with the failure mode above ("not measurable")
carrying the load when it does not match.

**Token custody.** The `dna-cloud` connection stores a refresh token that lives ~6 months,
encrypted, keyed by `oid`. Moving it into a product that reads customer source raises the
stakes on that store — revocation, scope, and audit become features, not implementation
details.

## What I would build first

The measurement, standalone: connect, point, report. No generation, no indexing, no model.
It is the smallest shippable thing, it reuses code already under CI, and it is the part with
no credible competitor. Generation and indexing follow for the customers who discover their
documentation is rotten — which the measurement is what tells them.

## References

- `apps/backend/app/modules/knowledge/internal/wiki_builder.py` — `_fidelity_report`, `gather_source`
- `apps/backend/eval/wiki_shelf_test.py` — the three questions, and why freshness is reported rather than enforced
- `dna-cloud`: `apps/web/lib/connections/github.ts` — the delegated GitHub connection
- [ADR-016](../../adr/ADR-016-openwiki-closes-the-freshness-loop.md) — how generation got here
- Prior art surveyed 2026-08-16: driftdev.sh (4★), GitHub search across three vocabularies (max 6★),
  MCCL / C4RLLaMA on code-comment inconsistency (different unit of analysis)
