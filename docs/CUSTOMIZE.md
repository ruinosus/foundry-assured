---
title: Make it yours — adapting the showcase to your domain
description: How to swap the four domain-specific pieces (corpus, prompts, action, identity) while keeping the Foundry plumbing as-is.
type: how-to
audience: adopter
status: stable
updated: 2026-06-27
---

# Make it yours — adapting the showcase to your domain

This project is a **pattern**, not just a helpdesk: **ask → ground → resolve → escalate**.
A developer asks, the system grounds an answer in a knowledge base, and escalates to a
human-approved action when answering isn't enough. That shape fits almost any internal
assistant — HR onboarding, legal Q&A, finance ops, customer success.

Swapping the domain means changing **four things**. Everything else — the multi-agent
workflow engine, AG-UI streaming, Entra auth/OBO, the eval harness, memory, tracing,
the deploy pipeline — is reusable Foundry plumbing you keep as-is.

| # | Swap point | Where | Kind |
| - | ---------- | ----- | ---- |
| 1 | **Knowledge corpus** | `apps/backend/app/knowledge/corpus/*.md` | drop-in |
| 2 | **Agent prompts** | `apps/backend/app/agents/prompts.py` | rewrite |
| 3 | **The action** (ticket → yours) | `apps/backend/app/tools/`, `workflow/escalation.py`, the `TICKET:` convention | rewrite |
| 4 | **Identity / labels** | `apps/frontend/lib/branding.ts`, `app/page.tsx` | set |
| 5 | **Eval datasets** | `apps/backend/eval/datasets/*.jsonl` | set (data only) |
| 6 | **Access (who sees each doc)** | your Entra groups + `COCKPIT_ACL_GROUP_MAP`; each source's read groups in the bundle manifest `groups` (or an external `{component: [group]}` map via `COCKPIT_ACL_CLASSIFICATION`) | set (data only) |
| 7 | **A whole new domain** (alongside helpdesk) | `apps/frontend/lib/domains.ts` + `apps/backend/app/agents/<domain>.py` + that domain's KB ingest | add |

> Rule of thumb: **#1, #4, #5, #6 you set; #2 and #3 you rewrite; #7 you add.** The
> rewrites are small (one prompts file, one tool) — that's the point. The eval *harness*,
> the ACL mechanism and the security gates never change — access is **data** (each
> source's read groups), not code. See [`METHOD.md`](./METHOD.md).

---

## 1 — Knowledge corpus (drop-in)

The grounded answers come from a Foundry IQ knowledge base built from markdown.

> **Corpus in PDF / Word / PowerPoint / HTML?** Convert it to Markdown first with
> Microsoft **[MarkItDown](https://github.com/microsoft/markitdown)** — there's a
> helper: `./scripts/to-markdown.sh -o apps/backend/app/knowledge/corpus *.pdf`
> (handles PDF, Office, HTML, and images via OCR). Then continue below.

1. Replace the files in `apps/backend/app/knowledge/corpus/` with **your** documents
   (plain markdown; one topic per file; the **filename/H1 title is what gets cited**).
   Delete the helpdesk runbooks.
2. *(optional)* Update the knowledge-source description in
   `apps/backend/app/knowledge/ingest.py` (the line that says
   `"Internal engineering runbooks and policies (helpdesk corpus)"`).
3. Re-ingest so the cloud KB reflects the new corpus:
   ```bash
   cd apps/backend && uv run python -m app.knowledge.ingest
   ```

That's the whole "what does it know" swap. No code changes.

---

## 2 — Agent prompts (rewrite — this is the brain)

All instructions live in **one file**: `apps/backend/app/agents/prompts.py`. There are
two consumers and both read from here:

- **The workflow** (`TRIAGE_/RETRIEVE_/RESOLVE_INSTRUCTIONS`) — the `triage → retrieve
  → resolve` steps.
- **The single concierge** (`CONCIERGE_*_INSTRUCTIONS`) — Phase 0/1 + the eval target.

Rewrite the prose for your domain. Keep these **invariants** or you'll break other pillars:

- **RETRIEVE** must still emit `NO_MATCH` when nothing is found, and **RESOLVE** must
  still *decline* (say "I don't know") on `NO_MATCH` rather than invent. The grounding
  eval (`eval/assertions.py`, "cites a source") depends on this.
- **RESOLVE** must still emit the single-line **`TICKET: <summary>`** signal when an
  action is needed — that's the contract the escalation step (#3) listens for. If your
  domain's action isn't "ticket", rename the keyword in *both* places (see #3).

> ⚠️ The **hosted agent** (`apps/hosted-agent/main.py`) is self-contained and can't import
> this file — it mirrors the same prompts inline. If you use the hosted-agent path, keep
> the two in sync (noted at the top of `prompts.py`).

---

## 3 — The action (rewrite — what "resolve" can *do*)

The helpdesk's escalation action is "open a ticket". The flow:

```
RESOLVE emits  "TICKET: <summary>"
   → workflow/escalation.py (EscalationExecutor) detects it → request_info (human approval)
       → on approval → app/tools/tickets.py create_ticket() persists + returns it
```

To make this **your** action (e.g. "book a meeting", "file an expense", "raise a PR"):

1. **The tool** — replace `apps/backend/app/tools/tickets.py`'s `create_ticket(...)` with
   your action (keep the shape: a plain function + a `tool(...)` wrapper for the hosted
   agent). Today it appends to `data/tickets.jsonl`; swap the body for your real backend
   call (or a different store — see [DEPLOYMENT.md › Cost & teardown](./DEPLOYMENT.md)).
2. **The trigger** — in `apps/backend/app/workflow/escalation.py`, the `EscalationExecutor`
   parses the `TICKET:` line and calls `create_ticket`. Point it at your tool and (if you
   renamed the keyword in #2) update the prefix it matches.
3. **The views** — `app/api/tickets.py` (`GET /tickets`) and the frontend
   `components/tickets/TicketsView.tsx` + `/tickets` route render the list. Rename/retheme
   or drop them if your action has no "list" view.

**No action at all?** If your assistant is pure Q&A, you can remove the `escalate` node
from the chain in `apps/backend/app/workflow/graph.py` (`.add_chain([triage, retrieve,
resolve])`) and tell RESOLVE never to emit `TICKET:`. The other pillars keep working.

---

## 4 — Identity / labels (set)

UI identity is centralized. Change the four strings in
**`apps/frontend/lib/branding.ts`** (`product`, `tagline`, `description`, `assistant`)
and the whole shell, login screen, browser title and nav re-skin.

Two pieces are **content**, not config — edit them directly:
- `apps/frontend/app/page.tsx` — the Overview hero copy + the "Capabilities" cards.
- *(optional)* the resource names in `apps/backend/app/core/settings.py`
  (`azure_search_knowledge_base`, `foundry_memory_store`, `hosted_agent_name`) — these
  are Azure resource names, not user-facing; only change them if you provision fresh.

---

## 5 — Evaluation datasets (swap the data, keep the harness)

The eval harness is reusable; only the **datasets** are domain-specific. Two JSONL
files in `apps/backend/eval/datasets/`:

**`golden.jsonl`** — one object per line, three fields:
```json
{"query": "<a real question your users ask>",
 "source": "<the H1 title of the corpus doc it should ground in>",
 "expected_output": "<one-line gist of the right answer>"}
```
The `source` must match one of **your** corpus doc titles — the runner feeds that
doc's text as grounding `context` for the Foundry judges, and the citation check
(`eval/assertions.py › cites_a_source`) **auto-derives** the valid titles from the
corpus (`*.md` H1s). So when you swap the corpus (#1), the citation check follows —
**no code change**. Just write ~10 questions that map to your new docs.

**`adversarial.jsonl`** — same shape; jailbreak / secret-leak prompts with
`"source": ""`. These are **domain-agnostic** (refuse-or-stay-grounded + never leak a
secret), so keep them as-is; add a few domain-specific attacks if you like.

Then validate:
```bash
cd apps/backend
uv run python -m eval.run_eval            # deterministic policy gate (blocks on fail)
uv run python -m eval.run_eval --cloud    # + Foundry groundedness/relevance/coherence
uv run python -m eval.run_eval --safety   # adversarial set
uv run python -m eval.run_eval --self-test  # proves the gate catches a planted violation (CI)
```
You do **not** touch `assertions.py`, `run_eval.py`, or the rubric unless you're
adding a new *policy* — the secret-leak and citation policies are domain-neutral.

---

## 7 — A whole new domain (add — keep helpdesk, run side-by-side)

Swap points #1–#6 *replace* the helpdesk. If instead you want to **add** another assistant
alongside it — the showcase ships three (helpdesk, cockpit, selfwiki) — domains are
**config-driven**. Adding one is three additions, no engine changes:

1. **Frontend** — add **one entry** to `apps/frontend/lib/domains.ts` (id, label, the
   backend agent path, branding). The domain selector and routing pick it up from there.
2. **Backend agent** — add `apps/backend/app/agents/<domain>.py` mirroring
   `apps/backend/app/agents/selfwiki.py` (its prompts + its knowledge source).
3. **Ingest** — point that domain's KB ingest at its corpus so its own Foundry IQ KB
   exists.

The workflow engine, AG-UI streaming, auth/OBO, eval harness, memory, tracing and deploy
are shared across all domains — you don't fork them per domain.

---

## Worked example — an "HR Onboarding Assistant"

1. **Corpus**: drop your onboarding/policy/benefits markdown into `knowledge/corpus/`,
   re-ingest.
2. **Prompts** (`prompts.py`): "helpdesk workflow" → "HR onboarding workflow"; "developer"
   → "new hire"; "runbooks" → "HR policies". Keep `NO_MATCH` + the decline rule.
3. **Action**: ticket → "open an HR case". Rename `TICKET:` → `CASE:` in RESOLVE's prompt
   **and** in `escalation.py`; rework `tools/tickets.py` into `create_case(...)`.
4. **Identity** (`branding.ts`): `product: "People Concierge"`, `tagline: "HR onboarding"`,
   `assistant: "Helper"`. Update the hero copy in `page.tsx`.
5. **Evals** (`eval/datasets/golden.jsonl`): swap in HR questions pointing at your new
   doc titles (e.g. `source: "Benefits enrollment"`); keep `adversarial.jsonl`.

Run it, sign in, ask "how do I enroll in benefits?" — grounded answer with citations; ask
"open a case to fix my payroll" → human-approved `create_case`. Same pillars, new domain.

---

## What you do **not** touch

The reusable Foundry plumbing — this is the value you're inheriting:

- `app/workflow/` (the `WorkflowBuilder` graph + AG-UI streaming + `stream_fix.py`)
- `app/core/auth.py` (Entra sign-in, OBO, memory scoping) — **including the RBAC**
  (Entra App Roles → Admin/Author/Approver/Reader + the `/admin/users` portal). It's
  reusable plumbing you configure (assign roles in Entra), not code you rewrite.
- `app/memory/` + the memory provider (managed Foundry memory)
- `eval/` harness — `assertions.py`, `run_eval.py`, the rubric (the policies are
  domain-neutral). You only swap the **datasets** — see §5 above.
- `infra/`, `azure.yaml`, `.github/workflows/` (provisioning + gated CI/CD deploy)
- the frontend shell, CopilotKit wiring, and the Live ⇄ Hosted toggle

See [`DEPLOYMENT.md`](./DEPLOYMENT.md) to provision and [`../README.md`](../README.md)
for the architecture overview.
