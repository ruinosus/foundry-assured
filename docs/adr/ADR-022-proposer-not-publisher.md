# ADR-022 — The proposer drafts; Foundry optimizes; only a human publishes

- **Status:** Proposed
- **Date:** 2026-08-18
- **Context:** [`apps/backend/app/modules/foundry/internal/assist.py`](../../apps/backend/app/modules/foundry/internal/assist.py),
  [`apps/backend/app/modules/foundry/internal/agent_write.py`](../../apps/backend/app/modules/foundry/internal/agent_write.py),
  [`apps/backend/app/modules/foundry/internal/skill_catalog.py`](../../apps/backend/app/modules/foundry/internal/skill_catalog.py)
- **Related:** [ADR-009](./ADR-009-native-tool-approval-foundry-connection-resolution.md) — write
  governance and native approval; [ADR-013](./ADR-013-declarative-agent-prompts-dna.md) — agent
  definitions as declarative data

## Context

The request, in the owner's words: *"um usuário vai criar um agent? certo. mas pra quê? porque
OUTRO agent pode criar esse… e um agent pode ACESSAR os agents que existem e até PROPOR."*

Part of this already exists. `assist.py` drafts and revises **one field** of the creation wizard
with the tenant's real catalog in context — knowing a knowledge base named `helpdesk-kb` exists is
what turns generic text into *"consult helpdesk-kb and cite the document"*. It established the
property this ADR must not lose: **text only enters the form by a human gesture**.

The step being asked for is to propose the **whole thing** — name, instructions, which knowledge
base, which skills, which of the existing agents could be reused — instead of one field.

Before designing that, the MÁXIMA MAIOR requires establishing what the platform already does.

## What was measured

`azure-ai-projects` ships an **agent optimization job**. Quoting the installed package:

> `OptimizationJob` — *"a long-running job that optimizes an agent's configuration (instructions,
> model, skills, tools) to maximize evaluation scores. On success, the result contains scored
> candidates."*

The shape of it matters as much as its existence:

| Piece | What it carries |
|---|---|
| `OptimizationJobInputs` | the **agent** (pinned version), a **train_dataset**, and **evaluators** — all required |
| `OptimizationCandidate` | `mutations` (e.g. `{system_prompt: …}`), `avg_score`, `avg_tokens`, `eval_id`, `eval_run_id` |
| `OptimizationCandidate.promotion` | *"Promotion metadata. **Null if the candidate has not been promoted**."* |

Two conclusions follow directly. First, **improving an existing agent is a solved, first-party
capability**, and it is scored against evaluations rather than asserted. Second, Microsoft drew the
same boundary this ADR needs: a candidate is produced, and **promotion is a separate act**.

Alongside it, `DataGenerationJob` generates datasets for evaluation — the input an optimization job
requires. The chain `generate data → optimize → scored candidates → promote` is entirely
first-party.

Both live under **`client.beta.*`** (`BetaAgentsOperations.begin_create_optimization_job`,
`BetaEvaluatorsOperations` / `BetaDatasetsOperations.begin_create_generation_job`) — the namespace
rule #1 names explicitly as the one that moves fastest.

### The gap, stated precisely

| Need | Covered by Foundry? |
|---|---|
| Improve an existing agent's instructions / model / skills / tools, scored | **Yes** — `OptimizationJob` |
| Produce an evaluation dataset to score against | **Yes** — `DataGenerationJob` |
| Keep proposal separate from publication | **Yes** — `candidate.promotion` is null until promoted |
| Propose an agent **that does not exist yet**, from a business need | **No** — optimization requires an agent, a dataset and evaluators |
| Choose **which** knowledge base and skills from this tenant's catalog | **No** — it mutates the configuration of an agent it is given |
| Do any of it for a user with no Azure RBAC and no portal access | **No** — and this is the product's reason to exist |

The first three rows are the reason this ADR exists: they are the parts we must **not** write.

## Decision

**The proposer has two paths, and neither of them publishes.**

**Path A — a new agent does not exist yet: we draft.** The proposer reads the tenant catalog
(agents, knowledge bases, skills, toolboxes) and returns a **draft**: proposed name, instructions,
which knowledge base to ground on, which skills to attach, and — explicitly — **which existing
agents already cover part of the need**. This is `assist.py` widened from one field to a form. It
is glue over a model call the repository already makes (`get_openai_client()` +
`responses.create`), not a new runtime.

**Path B — the agent exists and should get better: we do not touch it.** The proposer launches a
Foundry **optimization job** and renders the scored candidates, their mutations and their token
cost. We do not write a second prompt-improvement loop; ours would be unscored, and an unscored
"improvement" is a preference presented as a fact.

**Publication is never the proposer's.** It stays the existing admin-gated route
(`POST /foundry/agents/{name}/versions`), reached by a human acting on the draft. For Path B it
stays candidate promotion, likewise explicit.

### How the boundary is enforced, in code rather than in intent

Stating "the proposer only proposes" is worth nothing on its own — the whole risk is a future edit
that quietly adds a publish call to save a click. Three mechanisms, in increasing order of
strength:

1. **The HTTP surface.** Proposer routes return drafts and carry no write dependency. The publish
   route already requires the **Admin** role (RULE #5's governance, ADR-009).
2. **An architecture gate.** A test asserts the proposer module never references
   `create_agent_version`, `create_knowledge`, `create_skill*` or `delete_*`. This is the same
   family as `module_graph_test` and `filesystem_anchors_test`: a property that must not regress
   silently, checked every push.
3. **The draft is data, not a resource.** A proposal is returned to the caller and stored nowhere.
   Nothing to promote by accident, nothing to leak into a listing as if it were real.

## Consequences

**Gained.** A business user who cannot open the Azure portal gets a starting point built from what
their tenant actually has, and — for agents already live — Microsoft's own scored optimization
rather than our opinion of a better prompt.

**Accepted.** Path B depends on a **beta** surface. Rule #1 applies with force: no abstraction over
it, no wrapper that pretends stability. If the shape changes, one module changes. Path B also
requires a dataset and evaluators, which most tenants will not have on day one — the honest
behavior is to say so and offer `DataGenerationJob`, not to silently degrade into Path A.

**Refused.** A proposer that publishes on approval-in-the-chat. The approval primitives this
repository already has (tool-approval, the HITL card) govern **an agent's tool call**; a
resource-creation flow driven by an agent is a different blast radius, and ADR-009's write
governance was written for exactly that distinction.

**What would revisit this.** A first-party API that proposes an agent *from a description* against
the project catalog. If Foundry ships it, Path A becomes glue to it and most of this ADR's code
disappears — which is the outcome the MÁXIMA MAIOR wants, not one to defend against.
