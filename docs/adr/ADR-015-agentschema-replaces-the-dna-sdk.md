# ADR-015 — The agent definitions become AgentSchema, read by Microsoft's own reader

- **Status:** Accepted
- **Date:** 2026-08-13
- **Supersedes the mechanism of:** [ADR-013](./ADR-013-declarative-agent-prompts-dna.md)
  (the *decision* — instructions are declarative data, `prompts.py` is a shim —
  stands unchanged; only what reads the data changed) and the storage half of
  [ADR-014](./ADR-014-runtime-prompt-scope-no-rebuild.md) (`.dna/` → `agents/`,
  `DNA_BASE_DIR` → `AGENTS_DIR`, `/mnt/dna` → `/mnt/agents`)
- **Context:** [`apps/backend/agents/`](../../apps/backend/agents),
  [`apps/backend/app/agents/definitions.py`](../../apps/backend/app/agents/definitions.py),
  [`apps/backend/app/agents/prompts.py`](../../apps/backend/app/agents/prompts.py),
  [`apps/backend/eval/prompt_contract_test.py`](../../apps/backend/eval/prompt_contract_test.py)

## Context

ADR-013 externalized the agent instructions into declarative documents read by
the **DNA SDK**, and called itself "a deliberately small pilot". The pilot's
result is in: the *shape* was right — prompts are data, `prompts.py` is a shim,
contracts are machine-checked — and the *dependency* was not.

Measured before deciding anything:

- `dna-sdk>=0.1,<0.2`, resolved to **0.1.0**. The SDK's current version is
  **0.80** — 79 releases ahead of what this backend can accept.
- **One** file imported it: `app/agents/prompts.py`, line 102, `from dna import
  Kernel`. **Two** calls: `Kernel.quick(scope, base_dir=…)` and
  `build_prompt(agent=…)`.
- The price of being frozen was already written in the code, as a hand-rolled
  workaround: `build_prompt` on a missing agent **returns the string** `Agent
  '<x>' not found` instead of raising, so `prompts.py` had to assert the
  document's existence separately or a renamed YAML would have become the
  literal agent instruction.

Meanwhile the thing DNA was doing here — describe an agent declaratively — got a
standard: **[AgentSchema](https://github.com/microsoft/AgentSchema)**, with an
official reader on PyPI, `agent-framework-declarative`, from the same vendor as
the `agent-framework` this backend already runs on. Its `_models.py` *is* the
schema (`AgentDefinition`, `PromptAgent`, `Model`, `McpTool`, `FunctionTool`,
`Connection`).

## Decision

**Translate the eight agent documents to AgentSchema `PromptAgent`, read them
with Microsoft's official reader, and drop `dna-sdk`. Everything AgentSchema
does not model stays this repository's own data, with a small loader — because
it always was this repository's data.**

- **The eight agents** are now `agents/helpdesk/<name>.yaml`, `kind: prompt`, no
  `apiVersion` (AgentSchema's discriminator is `kind`). Field mapping:
  `metadata.name → name`, `metadata.description → description`,
  `spec.instruction → instructions`. `model` is deliberately **absent** although
  the schema marks it required: this backend owns model selection (its own
  Azure AI Foundry chat client), and naming a model id here would be data nobody
  reads. `tools` is absent on `platform` for the same kind of reason — its MCP
  servers are brokered per user and per tenant at request time (ADR-011), so a
  static list would name servers the caller may not be entitled to.
- **The reader is the official one**, per the house rule on market standards:
  `yaml.safe_load` → `agent_schema_dispatch` from
  `agent_framework_declarative._models`. The **private** module is imported
  deliberately: the package's only public surface, `AgentFactory`, builds an
  agent over a chat client, and this backend builds its own agents. The pin is
  therefore exact. (Both sibling migrations in this family landed on the same
  import and the same reasoning.)
- **What AgentSchema does not model did not get bent into it.** The schema
  describes one agent; four things here are not that, and each stayed data with
  a loader, saying so in its own file header:

  | concept | where | loader |
  |---|---|---|
  | the scope catalog (`defaultAgent`) | `agents/helpdesk/scope.yaml` | `definitions.load_scope` |
  | the shared concierge persona | `agents/helpdesk/personas/*.md` | `definitions.load_personas` |
  | cross-cutting rules (`## Guardrail:` sections) | `agents/helpdesk/guardrails/*.md` | `definitions.load_guardrails` |
  | the prompt-contract suite | `agents/helpdesk/eval-{cases,suites}/` | `eval/prompt_contract_test.py` |

  An agent points at a persona/guardrail **by name** from AgentSchema's standard
  `metadata` bag, under this repository's vendor key `x-foundry-assured`. That is
  the schema's own extension point, not an invented field.
- **Composition is one fixed order** — persona, `instructions`,
  `additionalInstructions`, then one section per wired guardrail. The DNA
  documents carried a per-agent `promptTemplate` override each, which existed
  only to reorder the SDK's default template; with the order stated once in the
  host, all six overrides disappear.
- **The refusals are kept and widened.** An unknown agent raises `AgentNotFound`
  (the workaround ADR-013 had to hand-roll is now the reader's own behavior); so
  does a dangling persona/guardrail reference, resolved eagerly at load rather
  than on the first request that composes that agent; an unknown schema field
  raises `TypeError` from the official model rather than being dropped in
  silence; and a composed prompt that comes out empty still refuses the boot.
- **PowerFx `=Env.X` is refused, not used.** The official reader hands any value
  starting with `=` to PowerFx and, when the .NET runtime is absent, **returns
  the literal string** with nothing but a log line — measured on a developer
  machine here: `_try_powerfx_eval("=Env.FOO")` → `'=Env.FOO'`. A secret name
  that silently becomes prose is exactly the failure mode this repository refuses
  elsewhere, so `definitions.refuse_powerfx_indirection` rejects such a value at
  load and says to resolve it in the host. No definition needs one today.
- **The eval suite came along.** It ran as `dna eval run helpdesk-prompts` from
  `dna-cli`; the cases were always this repository's contracts, so they stayed as
  YAML and `eval/prompt_contract_test.py` became their runner — same nine cases,
  same CI gate, one fewer tool. It carries four guards on itself (unknown agent
  raises, a failing check fails, `=Env.X` is refused, an unknown field is
  refused), because a green suite over a broken loader proves nothing.

## What the swap found

Composing the eight prompts both ways, byte for byte, showed the two readers
disagree on **five of eight**: the DNA composition appended the shared concierge
persona sentence — *"You are the Helpdesk Concierge, an internal engineering
support assistant…"* — to `triage`, `retrieve`, `resolve`, `cockpit` and
`selfwiki`, **none of which declares a persona**. The three that were spared
(`concierge-grounded`, `concierge-ungrounded`, `platform`) are exactly the three
that carried a `promptTemplate` override. The scope's single Soul was being
resolved into the Kind's default template for every agent that did not override
it, so the pt-BR Cockpit expert and all three workflow steps ended their prompt
introducing themselves as the Helpdesk Concierge.

It shipped that way from ADR-013 phase 2 and no case caught it, because every
check was positive: nothing asserted a prompt does **not** contain something it
was never given. Five `not_contains` checks now pin it.

**This is a behavior change**, not a faithful move: the five prompts lose that
trailing sentence. Composing only what an agent asks for is the intent ADR-013
phase 2 wrote down ("the shared persona… composed into the grounded and
ungrounded variants").

## Alternatives considered

- **Stay on `dna-sdk` 0.1.0.** Free today; the gap widens every release, the
  workaround for the string-instead-of-raise bug stays, and the format is legible
  to exactly one tool. Rejected — this is the problem.
- **Follow `dna-sdk` to 0.80.** Fixes the version gap, keeps a single-vendor
  format for a job that now has a standard, and re-opens a migration this size on
  every major. Rejected once AgentSchema existed.
- **`AgentFactory` (the reader's public surface).** It builds a chat-client agent
  from the YAML. This backend builds its own agents — workflow steps, AG-UI
  concierges, per-request tool brokering — so the factory would have to be
  bypassed anyway. Rejected in favor of the object model, with an exact pin.
- **Fold the personas and guardrails into each agent's `instructions`.** Removes
  every out-of-schema file, and duplicates the shared persona into two agents and
  each guardrail into every agent that carries it — the duplication ADR-013 phase
  2 removed. Rejected.
- **Model a guardrail as an AgentSchema field with a nearby meaning.** There
  isn't one, and picking the nearest would produce a document that lies to any
  other tool that reads it. Rejected — the point of adopting a standard is that
  strangers can read it.
- **`agent-framework-declarative==1.0.1` (the current release).** It requires
  `agent-framework-core>=1.13.0`, and this backend's `agent-framework-ag-ui`
  1.0.0rc5 does not survive that core — `ImportError: cannot import name
  '_try_execute_function_calls'`, which fails `eval.run_eval --self-test`, a
  required CI gate. Moving to 1.0.1 means moving `agent-framework` **and**
  `agent-framework-ag-ui` with it: a framework upgrade, not a schema-reader swap.
  Pinned at `1.0.0rc2` — the same object model, the same AgentSchema — and the
  upgrade gets its own change.

## Consequences

- **+** The definitions are in a published schema with an official reader, so
  another tool can read them. The instruction texts are unchanged (except the
  five that lose the leaked persona sentence).
- **+** One dependency out, and with it `aiofiles` and `chevron`; the two added,
  `agent-framework-declarative` and `pyyaml`, were already installed as
  transitive dependencies of `agent-framework`.
- **+** The refusal that ADR-013 had to hand-roll is now the reader's behavior,
  and dangling references fail at load instead of at first use.
- **+** A prompt-content defect that survived a year of green CI is fixed and
  pinned.
- **−** The migration is **bigger, not smaller**: the SDK carried a template
  engine, a document registry and an eval runner, and the parts of those this
  repository actually used had to be written down. The composition order, the
  front-matter reader and the eval runner are now ~600 lines of this repository's
  code that used to be somebody else's.
- **−** The private-module import (`agent_framework_declarative._models`) is a
  pin that must be revisited on every upgrade of that package. The alternative
  was the public factory, which builds the wrong thing.
- **−** Importing that package initializes PowerFx, which prints .NET
  diagnostics on stdout on a machine without the runtime it wants. The import is
  wrapped in `contextlib.redirect_stdout(sys.stderr)` so stdout stays the
  server's.
- **⚠ Operational, once:** an environment provisioned before this ADR has the old
  DNA scope on the `assured-prompts` share. The AgentSchema reader refuses it
  loudly (`apiVersion` is not a schema field), which is the correct outcome —
  run `scripts/push-prompts.sh --mirror` once to replace it.

## References

- [AgentSchema](https://github.com/microsoft/AgentSchema) ·
  [`agent-framework-declarative`](https://pypi.org/project/agent-framework-declarative/)
- [ADR-013](./ADR-013-declarative-agent-prompts-dna.md) — the decision this keeps
  and the mechanism it replaces
- [ADR-014](./ADR-014-runtime-prompt-scope-no-rebuild.md) — the no-rebuild loop,
  unchanged except for the directory and env-var names
