# Arquivo fornecido (verificado)

Arquivo: ASSURANCE-MECHANISM-PLAN.md (fornecido) — todas as afirmações abaixo estão extraídas desse arquivo.

## Metadados do arquivo
- title: KB → Agent Assurance Mechanism — Implementation Plan  
- description: The design and rationale for the assurance mechanism — its guarantees, gates, and intended work, for contributors.  
- type: plan  
- audience: contributor  
- status: draft  
- updated: 2026-06-27

(ASSURANCE-MECHANISM-PLAN.md)

## "North star" (trecho)
> A reusable mechanism any company points at one or more repositories / knowledge bases and gets three guarantees: (1) the KB is **built faithfully** from source, (2) the agent **answers correctly and completely** over it, and (3) **access is secure** — each caller only sees what they're entitled to, and the agent can't be hijacked or made to exfiltrate. It runs 100% on Microsoft Foundry and ships as a template + method, not a bespoke build.

(ASSURANCE-MECHANISM-PLAN.md)

## Princípios (trecho)
1. Verify against source. Neither the docs nor the eval golden are trusted because an LLM wrote them — both are checked against the real source. (The case-study meta-finding.)  
2. Guarantees are measured and gated, never asserted. Every phase has a 🟢/🔴 signal wired to a number, a CI gate, and a trace.  
3. Least-privilege, permission-aware by default. The agent retrieves under the caller's identity; org-wide single-identity is the exception, not the default.  
4. Generic & domain-swappable. Everything is parameterized (`--repo` / `--kb` / corpus + prompts), so the same pipeline documents any project.  
5. Never invent SDK signatures. The `.beta`/preview surfaces of `azure-ai-projects`, `agent-framework`, Foundry IQ and the eval/red-team SDKs move fast. Confirm against `learn.microsoft.com/azure/foundry` + `microsoft-foundry/foundry-samples` before fixing a call; leave an explicit `# TODO: verificar assinatura` otherwise.

(ASSURANCE-MECHANISM-PLAN.md)

## Activos existentes (trecho)
- `app/knowledge/wiki_builder.py` — generate→verify→ingest, claims cited to real files  
- `app/knowledge/ingest_cockpit.py` — indexer + `purge_orphans` reconciliation  
- `AzureAISearchContextProvider` (agentic) + `cockpit-kb` knowledge agent  
- `eval/run_eval.py` + `eval/assertions.py` + source-verified golden (gitignored)  
- Entra OBO on `/helpdesk` (per-user identity)  
- OTEL → Application Insights tracing  
- GitHub App release→gated-deploy, template, `CUSTOMIZE.md`

(ASSURANCE-MECHANISM-PLAN.md)

## Lacunas identificadas no arquivo (trecho)
O arquivo lista gaps que o mecanismo deve fechar:
- retrieval recall is unmeasured and untuned (Phase 2)  
- the eval isn't a gate and lacks completeness/recall evaluators (Phase 3)  
- the KB has no document-level security / identity-passthrough retrieval (Phase 4)  
- the agent is never red-teamed (Phase 5)  
- none of it is packaged as a generic method (Phase 6)

(ASSURANCE-MECHANISM-PLAN.md)

## Fases presentes no arquivo (trechos)
O arquivo descreve fases executadas em sequência; cada fase tem a estrutura "Objective → Build → Foundry/Azure pieces → Verify-at-impl (SDK) → Guarantee (🟢/🔴) → Acceptance."

- Phase 0 — Foundations: define the guarantees & the ruler  
  - Objective: Turn "answers well / securely" into numbers and gates before building, so every later phase has a target.  
  - Build: A single `assurance.config` (thresholds): `groundedness ≥ G`, `answer_completeness ≥ C`, `retrieval_recall ≥ R`, `citation_floor = 1`, `redteam_ASR ≤ A`; Golden discipline doc; Confirm traces already flow (OTEL → App Insights).  
  - Guarantee / Acceptance: `assurance.config` + golden-review checklist in repo; harness reads the thresholds.

- Phase 1 — Build the KB right (fidelity gate)  
  - Objective: Make "the KB is built the best way" a measurable gate.  
  - Build: generate → verify → ingest; Add a fidelity score per generated bundle (% claims that cite a real file (with line range) and survive the verifier); Keep `purge_orphans`.  
  - Guarantee / Acceptance: a bundle below the fidelity floor is rejected; index == container after ingest; Fidelity gate runs in the ingest path.

- Phase 2 — Retrieval completeness (close the recall gap)  
  - Objective: Guarantee nothing relevant is left out of retrieval.  
  - Build: Tune the `cockpit-kb` knowledge agent for recall (mentions `retrieval_reasoning_effort = medium`, `rerankerThreshold`, sub-query/output limits); Prompt exhaustiveness rule for enumeration; Measure with the Document Retrieval evaluator (recall/precision/NDCG) against an enumeration golden verified to source.  
  - Guarantee / Acceptance: `retrieval_recall ≥ R` on the enumeration golden; recall measured before/after tuning.

- Phase 3 — Answer-quality guarantee (the eval gate)  
  - Objective: Make "the agent answers correctly" a CI gate + a continuous prod monitor.  
  - Build: Extend `eval/run_eval.py` with Foundry evaluators: Groundedness, Answer/Response Completeness, Relevance, plus Retrieval evaluator; Grow the golden with source-verified questions; Wire the CI gate (`ai-agent-evals` action / FoundryEvals); Add continuous evaluation sampling prod traffic into Azure Monitor.  
  - Guarantee / Acceptance: a planted regression fails CI; prod scores visible per-trace.

(ASSURANCE-MECHANISM-PLAN.md)

- Phase 4 — Permission-aware access (secure retrieval)  
  - O arquivo contém o cabeçalho desta fase, mas o conteúdo fornecido está truncado neste ponto no arquivo fornecido.

(ASSURANCE-MECHANISM-PLAN.md)

---

Observação: todo o conteúdo acima é extraído diretamente do arquivo ASSURANCE-MECHANISM-PLAN.md fornecido. Não foram acrescentadas afirmações externas nem recomendações não presentes no arquivo.