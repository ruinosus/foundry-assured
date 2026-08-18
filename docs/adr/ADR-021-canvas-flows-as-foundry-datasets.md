# ADR-021 — Canvas flows are Foundry **Datasets**, not workflow agents — the field that looks right is a retiring format

- **Status:** Accepted
- **Date:** 2026-08-17
- **Context:** [`apps/backend/app/modules/foundry/internal/flow_store.py`](../../apps/backend/app/modules/foundry/internal/flow_store.py),
  [`apps/backend/app/modules/usecases/internal/usecases.py`](../../apps/backend/app/modules/usecases/internal/usecases.py),
  [`apps/frontend/lib/flowCanvas.ts`](../../apps/frontend/lib/flowCanvas.ts)
- **Related:** [ADR-014](./ADR-014-runtime-prompt-scope-no-rebuild.md) — the Azure Files mechanism
  this ADR deliberately does *not* reuse; [ADR-015](./ADR-015-agentschema-replaces-the-dna-sdk.md) —
  declarative definitions read by `agent-framework-declarative`

## Context

The use-cases layer gives a business reader a canvas: drag steps, connect them, save. The canvas
serializes to **Agent Framework declarative YAML** (`kind: Workflow` + `trigger` + `actions`),
which the backend validates by building it with the runtime's own `WorkflowFactory` before
accepting it.

That YAML was being written to `apps/backend/agents/helpdesk/workflows/<case>.yaml` — the
container's own disk. Two things are wrong with that. In production the disk is ephemeral, so a
flow assembled through the UI disappears at the next restart, silently and with no error. And a
product resource living outside the platform is exactly what the **SEGUNDA MÁXIMA** forbids:
*tudo fica no Foundry; muda quem colocou e como.*

The obvious fix was `WorkflowAgentDefinition`. The SDK ships it, it takes a YAML string, and its
name says workflow. It does not work, and the reason generalizes.

### What was measured

**1. The service validates the field, and rejects our YAML.**

```
client.agents.create_version(name, definition=WorkflowAgentDefinition(workflow=<AF YAML>))
→ HttpResponseError (invalid_payload) Invalid workflow definition.
  Exception Details: (ValidationError) Invalid workflow definition.
```

The YAML was not malformed: `agent_framework_declarative`'s factory accepts that exact shape
(`_workflows/_factory.py` documents `'kind'`, `'trigger'`, `'actions'`, optional `'agents'`). The
field is not a free-form blob — it expects a **different format**. The SDK docstring names it
"the CSDL YAML definition", and "CSDL" appears twice in the entire installed package, with no
schema and no example.

**2. That format is the portal designer's, and it is being retired.**

Microsoft's own page states: *"Microsoft Foundry is retiring workflows on December 1, 2026"*, and
directs users to Microsoft Agent Framework or Logic Apps. On the relationship between the two
formats it is careful rather than reassuring — exported workflow YAML runs in an Agent Framework
project *"with minimal changes"*, which is a migration note, not an equivalence.

So the field would require writing a translator, from our format into an undocumented one, whose
target has a removal date roughly three months out. That is work thrown away twice.

**3. The retirement is telling us where definitions belong.**

The direction is not "Foundry stopped storing workflows" but "in the Agent Framework model, the
workflow definition lives with *your* application." Foundry keeps the agents, the knowledge, the
connections, the toolboxes. The orchestration graph is the deployment's.

### Options considered

| Option | Why not |
|---|---|
| `WorkflowAgentDefinition` | Rejected by the service; format undocumented; **retires 2026-12-01** |
| Skill version (file bundle) | Would store the bytes — skills take arbitrary files and have `download_version` — but anyone opening the portal would find a "skill" that is not a skill. Storage is not the only requirement; being legible is one too |
| Azure Files, as ADR-014 does for prompts | The publishing path is `scripts/push-prompts.sh`: an **operator**, an **account key**, and definitions that compose **at boot**. Correct for prompts an engineer pushes; wrong for a business user pressing *Save* and expecting the next page load to show their flow |
| Azure Table, as the tenant store does | Durable and runtime-writable with managed identity, but a YAML document is not table data, and it puts the flow somewhere the platform cannot show |
| Agent `metadata` | Size-capped; a flow of any size does not fit |

### Datasets, measured end to end

`client.datasets` is a first-class project resource: versioned, uploaded through a temporary SAS,
read back through service-issued credentials. The full cycle was run against the live project
before the module was written:

```
pending_upload(name, version)     →  temporary container + write SAS
upload blob via the SAS           →  the YAML goes up
create_or_update(FileDataset…)    →  the version exists in the project
get_credentials + download        →  returns byte for byte
```

Round-trip through the product's own functions, **deleting the local cache before reading**, so
the service was the only possible source:

```
write #1 → version '1'   → read back 215 chars, marker present
write #2 → version '2'   → "latest" returns v2; "version 1" still returns v1
```

## Decision

**A canvas flow is stored as a Foundry Dataset named `<case>-flow`, one version per save.**

`app/modules/foundry/internal/flow_store.py` owns the cycle (`save_flow` / `load_flow`);
`usecases.write_flow` publishes there after the `WorkflowFactory` validation, and
`usecases.read_flow` reads the service **first**, falling back to the repo's on-disk copy so that
flows shipped in git still render in a freshly provisioned environment.

Two details are load-bearing and easy to get wrong:

- **The SAS is not in `blob_uri`.** It arrives separately as `blob_reference.credential.sas_uri`;
  uploading against `blob_uri` fails with `NoAuthenticationInformation`.
- **Version ordering is numeric, not lexical.** With ten versions, string ordering puts `"10"`
  before `"9"` and the screen would show an *older* flow with no error appearing anywhere.

## Consequences

**Gained.** Version history for free — versions do not overwrite, so what changed and when is
recoverable, and the portal shows what the screen shows. Auth stays `DefaultAzureCredential`
throughout, with no account key anywhere in the path (rule 2, ADR-005). Tenant prefixing comes
from the existing `qualify()`, so two tenants cannot collide on a flow name.

**Accepted.** One dataset per use case with a flow, which is a resource a reader will see in the
project listing; it is named for what it is. A save is three service calls, not one — acceptable
for a human pressing a button, and it is not on any request-serving path.

**Kept.** The on-disk copy survives as a boot-time fallback and as the git-versioned source of the
flows this repository ships. It is a cache, and `write_flow` treats a disk failure as non-fatal:
the publish already succeeded, and failing after it would turn a good save into an error.

**What would revisit this.** A first-party Foundry surface for storing Agent Framework workflow
definitions. If one ships, it wins by the MÁXIMA MAIOR and this module becomes the glue to it.
Datasets are the correct answer to "where does a versioned definition file live in a Foundry
project today", not a claim that a better answer cannot exist.
