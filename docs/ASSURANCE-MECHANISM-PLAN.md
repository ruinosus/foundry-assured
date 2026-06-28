---
title: KB → Agent Assurance Mechanism — Implementation Plan
description: The design and rationale for the assurance mechanism — its guarantees, gates, and intended work, for contributors.
type: plan
audience: contributor
status: draft
updated: 2026-06-27
---

# KB → Agent Assurance Mechanism — Implementation Plan

> **North star.** A reusable mechanism any company points at one or more repositories /
> knowledge bases and gets three guarantees: (1) the KB is **built faithfully** from
> source, (2) the agent **answers correctly and completely** over it, and (3) **access is
> secure** — each caller only sees what they're entitled to, and the agent can't be
> hijacked or made to exfiltrate. It runs 100% on Microsoft Foundry and ships as a
> template + method, not a bespoke build.

## On "100% efficacy" (read this first)

A literal 100% is not honest to promise — small judge-scored evals catch regressions,
they don't certify absolute truth. What this mechanism delivers, and what passes a
multinational's audit, is a **measured, gated guarantee**: groundedness / completeness /
retrieval-recall thresholds enforced in CI, continuous evaluation on production traffic,
and a red-team Attack-Success-Rate kept under a ceiling. "100%" expressed as controls.

## Principles (non-negotiable)

1. **Verify against source.** Neither the docs nor the eval golden are trusted because an
   LLM wrote them — both are checked against the real source. (The case-study meta-finding.)
2. **Guarantees are measured and gated**, never asserted. Every phase has a 🟢/🔴 signal
   wired to a number, a CI gate, and a trace.
3. **Least-privilege, permission-aware by default.** The agent retrieves under the
   caller's identity; org-wide single-identity is the exception, not the default.
4. **Generic & domain-swappable.** Everything is parameterized (`--repo` / `--kb` /
   corpus + prompts), so the same pipeline documents any project.
5. **Never invent SDK signatures.** The `.beta`/preview surfaces of `azure-ai-projects`,
   `agent-framework`, Foundry IQ and the eval/red-team SDKs move fast. Confirm against
   `learn.microsoft.com/azure/foundry` + `microsoft-foundry/foundry-samples` before
   fixing a call; leave an explicit `# TODO: verificar assinatura` otherwise.

## What already exists (we build ON this, not rebuild)

| Asset | Pillar it serves |
| --- | --- |
| `app/knowledge/wiki_builder.py` — generate→verify→ingest, claims cited to real files | 1 (build right) |
| `app/knowledge/ingest_cockpit.py` — indexer + `purge_orphans` reconciliation | 1 |
| `AzureAISearchContextProvider` (agentic) + `cockpit-kb` knowledge agent | 2 (retrieve) |
| `eval/run_eval.py` + `eval/assertions.py` + source-verified golden (gitignored) | 3 (eval) |
| Entra OBO on `/helpdesk` (per-user identity) | 4 (secure access) — identity half only |
| OTEL → Application Insights tracing | 3/5 (observability) |
| GitHub App release→gated-deploy, template, `CUSTOMIZE.md` | 6 (package) |

The gaps the mechanism must close: **retrieval recall is unmeasured and untuned (Phase
2)**, **the eval isn't a gate and lacks completeness/recall evaluators (Phase 3)**, **the
KB has no document-level security / identity-passthrough retrieval (Phase 4)**, **the
agent is never red-teamed (Phase 5)**, and **none of it is packaged as a generic method
(Phase 6)**.

---

# The phases (execute in sequence; each gates the next)

Each phase: **Objective → Build → Foundry/Azure pieces → Verify-at-impl (SDK) → Guarantee
(🟢/🔴) → Acceptance.**

## Phase 0 — Foundations: define the guarantees & the ruler

**Objective.** Turn "answers well / securely" into numbers and gates before building, so
every later phase has a target.

**Build.**
- A single `assurance.config` (thresholds): `groundedness ≥ G`, `answer_completeness ≥ C`,
  `retrieval_recall ≥ R`, `citation_floor = 1`, `redteam_ASR ≤ A`. Start lenient,
  ratchet up.
- Golden discipline doc: every golden answer carries a **source pointer** (file/line or
  component+doc) and is reviewed against source before it can gate.
- Confirm traces already flow (OTEL → App Insights) so eval scores can be tied to runs.

**Guarantee.** 🟢 thresholds + golden-review checklist committed; a deliberately-planted
bad answer is caught by the harness. 🔴 numbers exist but nothing references them.

**Acceptance.** `assurance.config` + golden-review checklist in repo; harness reads the
thresholds.

## Phase 1 — Build the KB right (fidelity gate)

**Objective.** Make "the KB is built the best way" a measurable gate, not a vibe.

**Build.**
- Keep generate (`wiki-page-writer` depth rules) → **verify** (re-ground every claim
  against source, drop unsupported) → ingest.
- Add a **fidelity score** per generated bundle: % claims that cite a real file (with line
  range) and survive the verifier. Gate ingestion on it.
- Keep `purge_orphans` so the index never drifts from the container (reconciliation).

**Foundry/Azure.** Foundry IQ KB + blob knowledge source; the indexer.

**Verify-at-impl.** The bundle manifest schema the ingester already consumes; the
verifier-pass call shape.

**Guarantee.** 🟢 a bundle below the fidelity floor is rejected; index == container after
ingest. 🔴 lossy pages reach the KB silently.

**Acceptance.** Fidelity gate runs in the ingest path; a planted unsupported claim is
dropped and logged.

## Phase 2 — Retrieval completeness (close the recall gap)

**Objective.** Guarantee nothing relevant is left out of retrieval — the concrete bug
today (asked for all MCP servers, the agent listed 6 of ~9, retrieval surfaced 7 of 12
families).

**Build.**
- Tune the `cockpit-kb` knowledge agent for **recall**: `retrieval_reasoning_effort =
  medium` (enables iterative search — Microsoft's tests showed large completeness gains),
  review `rerankerThreshold` (lower → more docs pass), and the sub-query / output limits.
- Prompt **exhaustiveness rule** for enumeration ("when asked to list *all*, sweep every
  retrieved component, don't drop any; distinguish server vs SDK vs client").
- Measure with the **Document Retrieval** evaluator (recall/precision/NDCG) against an
  enumeration golden whose expected set is the source-verified component inventory.

**Foundry/Azure.** Knowledge-agent retrieval config (effort, reranker, sub-queries);
`AzureAISearchContextProvider`.

**Verify-at-impl.** Where `retrieval_reasoning_effort` / reranker threshold are set on the
knowledge agent (definition vs per-request); the Document Retrieval evaluator name + I/O.

**Guarantee.** 🟢 `retrieval_recall ≥ R` on the enumeration golden; the "list all MCP
servers" answer is complete and correctly typed. 🔴 recall unmeasured or below floor.

**Acceptance.** Recall measured before/after tuning; the MCP-enumeration question returns
the full, correctly-classified set.

## Phase 3 — Answer-quality guarantee (the eval gate)

**Objective.** Make "the agent answers correctly" a CI gate + a continuous prod monitor.

**Build.**
- Extend `eval/run_eval.py` with Foundry evaluators: **Groundedness**, **Answer/Response
  Completeness**, **Relevance**, plus the Phase-2 **Retrieval** evaluator.
- Grow the golden with the 8 source-verified Cockpit questions (enumeration,
  disambiguation server×SDK, per-server detail, anti-hallucination) + per-domain seeds.
- Wire the **CI gate** (`ai-agent-evals` action / FoundryEvals) — merges blocked below
  thresholds. Add **continuous evaluation** sampling prod traffic into Azure Monitor.

**Foundry/Azure.** Foundry Evaluations (azure-ai-projects 2.0 GA evaluators); continuous
eval; Azure Monitor dashboards.

**Verify-at-impl.** Exact evaluator classes/signatures in `azure-ai-projects` 2.0; the
`ai-agent-evals` action inputs; continuous-eval wiring.

**Guarantee.** 🟢 a planted regression fails CI; prod scores visible per-trace. 🔴 evals
run but gate nothing.

**Acceptance.** A bad answer blocks a PR; the dashboard shows live groundedness/completeness.

## Phase 4 — Permission-aware access (secure retrieval)

> **Shipped data-driven.** Access is the source's read **`groups`** (inherited from the
> origin repo/ACL or declared in an external map), resolved name→Entra-id via config —
> **no tiers and no classification logic in code**. For the as-built model, see
> [`METHOD.md`](./METHOD.md); the framing below is the original plan.

**Objective.** "Security for whoever uses it": each caller only retrieves documents they're
entitled to — enforced at query time, not by prompt.

**Build.**
- Move the KB to a **document-level-security** knowledge source: ACLs (and/or RBAC scopes)
  attached to each document at ingest.
- **Identity passthrough** — run retrieval under the caller's Microsoft Entra identity
  (extend the existing OBO from the endpoint into the retrieval call), so Foundry IQ trims
  results to that user's permissions.
- Access-control **evals**: user A must not retrieve user B's restricted docs; a public
  user gets only public docs. This is a *security* golden, gated like quality.

**Foundry/Azure.** Foundry IQ permission-aware retrieval (document-level ACL sync +
query-time trimming); identity-passthrough header / caller-identity mode; Entra OBO.

**Verify-at-impl.** How ACLs are attached on the knowledge source; how the
`AzureAISearchContextProvider` / knowledge-agent passes the caller identity (the
`x-ms-query-source-authorization`-style header or the SDK equivalent); the OBO→retrieval
plumbing.

**Guarantee.** 🟢 a restricted doc never appears for an unauthorized caller (proven by the
access-control eval). 🔴 retrieval is single-identity / org-wide where it shouldn't be.

**Acceptance.** Two test identities with different entitlements; retrieval provably trims
per identity; the negative case is a CI gate.

## Phase 5 — Agent defense (red-teaming gate)

**Objective.** A malicious document in an indexed repo can't hijack the agent or exfiltrate
data; the "lethal trifecta" is contained.

**Build.**
- Run the **AI Red Teaming Agent** against the live agent across categories: direct/indirect
  prompt injection (poisoned KB doc), instruction override, sensitive-data leakage,
  cross-context contamination. Measure **Attack Success Rate** per category.
- Defenses: **Prompt Shields / content safety** on retrieved content; system-prompt
  guardrails; output checks. Re-measure ASR after.
- Add an **ASR gate** to CI (merges blocked above the ceiling), and a seeded poisoned-doc
  regression test.

**Foundry/Azure.** AI Red Teaming Agent (PyRIT-backed); Prompt Shields / Azure AI Content
Safety; Foundry safety evaluators.

**Verify-at-impl.** AI Red Teaming Agent SDK (scan setup, risk categories, ASR output);
Prompt Shields call on retrieved chunks.

**Guarantee.** 🟢 `redteam_ASR ≤ A` across categories; a planted KB injection is neutralized.
🔴 the agent follows an injected instruction or leaks a restricted doc.

**Acceptance.** ASR report per category under ceiling; the poisoned-doc test is a CI gate.

## Phase 6 — Generalize & package the mechanism

**Objective.** Turn the cockpit-specific build into the reusable **mechanism** — the
"what / how / how-used" any company runs on its own repos/KB.

**Build.**
- Parameterize end-to-end (`--repo` / `--kb` / corpus + prompts + identities), so nothing
  is hard-coded to Cockpit. Confirm the four swap points (`CUSTOMIZE.md`) still hold with
  Phases 4–5 added.
- A **METHOD doc**: the pipeline, the gates, the thresholds, the identities — with a
  one-command bring-up (`azd up` + bootstrap + the assurance gates) for a new KB.
- Fold the new gates (recall, completeness, access-control, red-team) into the **template**
  and the release→deploy automation, so a fresh clone inherits the guarantees.

**Guarantee.** 🟢 a second, unrelated repo/KB goes through the whole pipeline with the same
gates and zero Cockpit-specific code. 🔴 the mechanism only works for Cockpit.

**Acceptance.** A dry-run on a different corpus reaches "answers + secure + gated" using
only parameters + docs.

---

## Sequencing & dependencies

```
0 Foundations ─► 1 Build-right ─► 2 Recall ─► 3 Eval-gate ─┐
                                                            ├─► 6 Package
                         4 Permission-aware access ─► 5 Red-team ─┘
```

- **0 → 1 → 2 → 3** is the quality spine (do first; 2 also fixes the live MCP complaint).
- **4 → 5** is the security spine; 4 (access) must precede 5 (red-team) because leakage
  tests need real entitlements to violate.
- **6** consumes all of them. 3 and 4 can overlap once 2 lands.

## Cross-cutting

- **Observability** (OTEL → App Insights) underpins Phases 3 & 5 — already wired.
- **Internal content stays gitignored** (corpus + goldens, incl. the security goldens);
  only code/config/method is committed. (Public repo.)
- **Cost.** Azure AI Search runs ~24/7 (~$0.10/h); `azd down --purge` between sessions.
- **Budget guard.** Each phase is independently testable; we don't advance without its 🟢.

## Open items to confirm via docs/samples (Rule #5)

- Foundry IQ knowledge-agent: where `retrieval_reasoning_effort` / `rerankerThreshold` live
  (definition vs per-request) — Phase 2.
- `azure-ai-projects` 2.0 evaluator classes for Completeness + Document Retrieval — Phase 3.
- Document-level ACL attachment + identity-passthrough retrieval signature — Phase 4.
- AI Red Teaming Agent SDK + Prompt Shields call surface — Phase 5.
