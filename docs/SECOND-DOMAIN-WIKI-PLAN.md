# Second domain (Cockpit expert) + the LLM Wiki pattern on Foundry — macro plan

The living plan for adding a **second domain** to the showcase: a *Cockpit platform
expert* agent that demonstrates the **LLM Wiki** pattern (generate + consume)
end-to-end, **100% on Microsoft Foundry**, using the **open Agent Skills (`SKILL.md`)
standard** and Microsoft's `deep-wiki` skill suite.

> Why it matters: it applies the showcase's own extensibility recipe
> ([CUSTOMIZE.md](./CUSTOMIZE.md)) to a real, large corpus — and adds the
> *self-improving* angle (a Foundry agent that generates a faithful wiki from source,
> measured against a source-verified golden set).

## The two sides

```
 SOURCE ──[ Wiki Builder agent  + deep-wiki skills: wiki-architect / wiki-page-writer / wiki-llms-txt ]──► faithful WIKI (cited)
                                                                                                              │
                                                                                          ingest → Foundry IQ KB (cockpit-kb)
                                                                                                              │
 QUESTION ──[ Cockpit agent + grounded-qa skill (adapted from deep-wiki wiki-qa), via SkillsProvider ]────────┘──► cited answer
                                                                                                              ▲
                                                                                       measured by the GOLDEN (source-verified)
```

- **Consume / retrieve** — a grounded agent answers over the KB, using a retrieval
  **Skill** for the citing/decline/authority discipline (not hand-rolled prompts).
- **Generate** — a **Wiki Builder** agent reads the *real source* (file tools) and
  writes a faithful, cited wiki in the bundle format the ingestion already consumes —
  fixing the fidelity gaps of hand/LLM-summarized docs, automatically.

### Two generation paths, one consumption

The *generate* side has **two interchangeable paths** — both driven by Microsoft's
open Agent Skills (`SKILL.md`) standard, both feeding the same `cockpit-kb`. The
*consumption* (Foundry IQ + the grounded agent), the eval, memory and HITL stay 100%
on Foundry regardless of which generator produced the wiki. This is the open-standard
point: the **same `deep-wiki` skills run in different runtimes**.

| | **Path 1 — Foundry workflow** (`wiki_builder.py`) | **Path 2 — Copilot CLI (native deep-wiki)** |
| --- | --- | --- |
| How | `agent-framework` + `FoundryChatClient` reads the same `SKILL.md` depth rules, paced pipeline | `/plugin marketplace add microsoft/skills` → `/plugin install deep-wiki@skills` → `/deep-wiki:generate` |
| Fidelity | bounded context (avoids TPM 429s) | agentic, real file tools (traces code paths) |
| Cost | pay-per-token (Foundry) | the developer's GitHub Copilot subscription |
| Strength | **automatable / hosted** (CI, hosted agent) | **interactive, highest fidelity**, the Microsoft-native deep-wiki UX |
| Output | already the ingest bundle (manifest + pages + llms.txt) | VitePress/markdown + `llms.txt` → a thin adapter maps it to the bundle |

Path 2 is the way [Microsoft ships deep-wiki](https://github.com/microsoft/skills/tree/main/.github/plugins/deep-wiki)
(a Copilot CLI plugin); Path 1 wraps the *same* skill rules so generation can run as an
automatable Foundry workflow. Use Path 2 for a one-off, max-fidelity, zero-budget run on
a dev machine; use Path 1 when generation must be hosted/scheduled.

## Key decisions

- **Knowledge**: Foundry IQ (Azure AI Search agentic retrieval), a **separate KB**
  (`cockpit-kb`) sharing the existing Search service — no new infra.
- **Agents**: `agent-framework` + `FoundryChatClient` (same engine as the helpdesk).
- **Skills**: the open **`SKILL.md`** standard via `SkillsProvider` / `FileSkillsSource`.
  Microsoft, Anthropic and OpenAI all converged on this format; Microsoft's
  [`deep-wiki`](https://github.com/microsoft/skills/tree/main/.github/plugins/deep-wiki)
  is the purpose-built suite for codebase→wiki (both sides). We adapt its skills rather
  than hand-rolling prompts.
- **Quality loop**: a **golden set verified against the real source** + an
  LLM-judge measurement harness → iterate (corpus, instructions, skill) → re-measure.
- **Internal content stays out of this public repo**: the Cockpit corpus and the
  golden set are read from an external path and shipped to the cloud KB only
  (gitignored). Only *code* (ingestion, agent, skills, wiring) is committed.
- **Budget**: the dominant meter is Azure AI Search (~24/7) — `azd down` between
  sessions; tokens for ingestion/iteration/evals are cents.

## Status

| Piece | State |
| --- | --- |
| Phase A — ingest corpus → `cockpit-kb` (Foundry IQ) | ✅ merged (PR #33) |
| Corpus enrichment with authoritative source docs | ✅ (cloud KB only) |
| Phase B — Cockpit agent + `/cockpit` endpoint + frontend route/nav | 🟡 done, **uncommitted** |
| `grounded-qa` retrieval **Skill** (from MS `wiki-qa`) via `SkillsProvider` | 🟡 done, **uncommitted** |
| Golden set (20, source-verified) + measurement harness | ✅ (gitignored) |
| Quality (consume) | **17/20** (hand-tuned); the `grounded-qa` skill holds (≥17/20) |
| **Wiki Builder D1** — generate a faithful bundle from source | ✅ **proven** (see below) |

### Wiki Builder — proven (D1)

`app/knowledge/wiki_builder.py` generates a faithful bundle from a repo, on Foundry:
deterministic source read → **plan** (one call) → **write** each page (Microsoft
`wiki-page-writer` depth rules: cite the real file, no guessing) → **verify** (re-ground
each claim against source, drop the unsupported) → assemble manifest + pages + llms.txt.
Paced + bounded so it stays under the model TPM cap. `--model` is configurable
(`gpt-5-codex` for max code fidelity); `--no-verify` to skip the verifier.

**Cost instrumentation (Microsoft pattern).** Each run prints a token+R$ rollup read
from the response's gen_ai usage (`usage_details.input/output_token_count`) — the same
data the OpenTelemetry **GenAI semantic conventions** capture. When
`APPLICATIONINSIGHTS_CONNECTION_STRING` is set, the build also exports those spans to
Application Insights (`configure_azure_monitor` + `enable_instrumentation`) so they show
in the Foundry *Tracing* / App Insights "Agents" view — off by default, zero infra.
The loadbalancer D1 run measured ~161K in + ~26K out across 13 `gpt-5-codex` calls ≈ R$2.5.

Verdict on `cockpit-openai-loadbalancer` (gpt-5-codex + verify): 6 pages, every page
verified, claims cited to real files **with line ranges** (`src/YarpConfiguration.cs:95-123`,
`src/RetryMiddleware.cs:22-51`, …) — far more faithful than the LLM-summarized docbundle.
Generic via `--repo/--component/--model` → the reusable protocol for any multi-repo project.

## Roadmap (in order)

1. **Commit Phase B + the `grounded-qa` skill** — consolidate what's done (this plan
   doc included). Corpus + golden stay gitignored.
2. **Wiki Builder (the generate side)** — the main remaining work:
   - **D1**: a Foundry agent + **file tools** (`read_file`/`list_dir`/`search_code`)
     + Microsoft `deep-wiki` generation skills (`wiki-architect`, `wiki-page-writer`,
     `wiki-llms-txt`) → generate a *faithful* wiki bundle for **one** component →
     prove fidelity beats the existing docs on the golden.
   - **D2**: run across components; assemble manifests; emit `llms.txt`.
   - **D3**: incremental mode (`--since <git-ref>` → regenerate only changed pages).
   - **Close the loop**: re-ingest the Foundry-generated wiki → re-measure → expect the
     remaining fidelity gaps to close.
3. **Phase C — hosted agent**: package the Cockpit agent as a managed Foundry hosted
   agent (like `helpdesk-concierge`).
4. **Eval wiring**: turn the golden + harness into a Cockpit-agent eval
   (FoundryEvals / the `ai-agent-evals` action), local/gitignored (internal data).

## Key files

```
apps/backend/app/knowledge/ingest_cockpit.py   # Phase A: corpus → cockpit-kb (reads external COCKPIT_DOCBUNDLES)
apps/backend/app/agents/cockpit.py             # Cockpit agent (search + grounded-qa skill)
apps/backend/app/agents/skills/grounded-qa/    # the retrieval Skill (SKILL.md), adapted from MS wiki-qa
apps/backend/app/agents/prompts.py             # COCKPIT_INSTRUCTIONS (identity; discipline lives in the skill)
apps/backend/app/main.py                       # registers /cockpit (auth-gated) when cockpit-kb is configured
apps/frontend/{app/cockpit, components/cockpit} # the /cockpit route + chat
# gitignored / external (internal content): the Cockpit corpus + eval/datasets/cockpit_golden.jsonl
# planned: apps/backend/app/knowledge/wiki_builder.py + skills (deep-wiki) — the generate side
```
