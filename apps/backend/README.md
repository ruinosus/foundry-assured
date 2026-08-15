# Foundry Assured — backend

FastAPI + Microsoft Agent Framework, exposing the agent domains over AG-UI:

- **`/helpdesk`** — the multi-agent workflow (triage → retrieve → resolve →
  escalate, with HITL).
- **`/cockpit`** — grounded Q&A over the `cockpit-kb` corpus.
- **`/selfwiki`** — grounded Q&A over a deep-wiki generated from this repo's own
  source.

`/cockpit` and `/selfwiki` register only once their KB is ingested + configured.
The `/admin/*` (user + role management via Microsoft Graph) and `/me` endpoints back
the Entra App Roles RBAC (Admin / Author / Approver / Reader).

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --port 8000 --reload
```

### Where the agent instructions live (ADR-013/ADR-015)

`agents/helpdesk/` holds one [AgentSchema](https://github.com/microsoft/AgentSchema)
`PromptAgent` document per agent, read with Microsoft's own reader
(`agent-framework-declarative`) and composed by `app/agents/prompts.py` at import.
**To change a prompt, edit the YAML — not the Python.**

What AgentSchema does not model stays this repository's data next to it, each
file saying so in its own header:

| concept | where | why not AgentSchema |
|---|---|---|
| the scope catalog (`defaultAgent`) | `agents/helpdesk/scope.yaml` | the schema describes one agent, not a directory of them |
| the shared concierge persona | `agents/helpdesk/personas/*.md` | the schema has no shared-identity document |
| cross-cutting rules (`## Guardrail:` sections) | `agents/helpdesk/guardrails/*.md` | the schema has no guardrail concept |
| the prompt-contract suite | `agents/helpdesk/eval-{cases,suites}/` | the schema describes an agent, not a test of one |

An agent references a persona/guardrail **by name** from AgentSchema's standard
`metadata` bag under the `x-foundry-assured` key; `app/agents/definitions.py`
composes them in one fixed order — persona, instructions, guardrails. An unknown
agent, a dangling reference or an unknown schema field **fails the boot**; none
of them may become the instruction.

`=Env.X` PowerFx indirection is **refused** at load: without the .NET runtime the
official reader returns the literal string in silence, so anything the definitions
need from the environment is resolved by the host instead.

### Container run — prompt edits without a rebuild (ADR-014)

`compose.yaml` runs the same image the deploy uses, but bind-mounts the
working-tree `agents/` over the baked-in copy, so editing a prompt YAML needs
a **restart, not a rebuild**:

```bash
docker compose up -d                     # build once, run
$EDITOR agents/helpdesk/cockpit.yaml     # change a prompt
docker compose restart backend           # restart picks it up — no image build
```

Prompts compose at import (`app/agents/prompts.py`) and agents are built at
boot, so a restart is the refresh unit — see
[ADR-014](../../docs/adr/ADR-014-runtime-prompt-scope-no-rebuild.md).

In **production** (azd/ACA) the same loop goes through an Azure Files share
mounted read-only at `/mnt/agents` and selected via `AGENTS_DIR` (ADR-014,
production leg). Publish with:

```bash
$EDITOR agents/helpdesk/cockpit.yaml            # change a prompt
uv run python -m eval.prompt_contract_test      # content gate (CI runs it too)
../../scripts/push-prompts.sh                   # upload + revision restart — no image build
```

Set `AGENTS_DIR` to point the backend at any external definition directory: if
`$AGENTS_DIR/helpdesk` exists it wins (and a broken directory fails the boot
loudly); if it is absent (empty/unseeded share) the backend logs a warning and
falls back to the copy baked into the image, so a fresh provision never
crash-loops. Unset means the baked-in copy.

Auth is always `DefaultAzureCredential` (Foundry/KB/memory); user requests carry an
Entra token (OBO + the `roles` claim). See the root [README](../README.md) and
[CLAUDE.md](../CLAUDE.md).
