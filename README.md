# Foundry Helpdesk

Internal engineering support concierge — a Microsoft Foundry showcase exercising
workflow, knowledge base, memory, and eval, with a CopilotKit frontend over the
**AG-UI** protocol. See [`foundry-helpdesk-spec.md`](./foundry-helpdesk-spec.md)
for the full build spec and [`CLAUDE.md`](./CLAUDE.md) for the working rules.

## Status

- **Phase 0** — hello-world over AG-UI. ✅ Round-trip green (CopilotKit → AG-UI → Foundry `gpt-4.1-mini`).
- **Phase 1** — Foundry IQ knowledge base. Code-complete; grounds answers in a
  runbook corpus via Azure AI Search agentic retrieval, cites sources, says "I
  don't know" off-corpus. Green after `azd up` + ingestion (steps below).

The backend falls back to the Phase 0 (ungrounded) behavior when the knowledge
base env vars are absent, so it always boots.

## Layout

```
backend/    FastAPI + Agent Framework, AG-UI endpoint at /helpdesk
  app/knowledge/corpus/   ~12 fake runbook markdowns (the KB corpus)
  app/knowledge/ingest.py blob upload + knowledge source + knowledge base
frontend/   Next.js 15 (App Router) + CopilotKit chat
infra/      Bicep (azd): Foundry + AI Search + Storage + embedding + RBAC
azure.yaml  azd config (provision-only — no services yet)
```

## Run locally

### 1. Provision Foundry with azd (required for live replies)

```bash
azd auth login
azd up        # prompts for env name + location; provisions everything in infra/
```

`azd up` creates a resource group `rg-<env>`, a Foundry account
`aif-helpdesk-<token>`, the project **`helpdesk-concierge`**, a `gpt-4.1-mini`
deployment, and grants your user the **Azure AI User** data-plane role (without
it, inference returns 401). Pick a region where `gpt-4.1-mini` GlobalStandard is
available (e.g. `eastus2`). Lower `modelCapacity` in `infra/resources.bicep` if
you hit a quota error.

Phase 1 also provisions **Azure AI Search (Basic, ~$0.10/hr)**, a Storage
account, and a `text-embedding-3-large` deployment, with keyless RBAC. AI Search
is billed per hour the service exists — run `azd down` when you finish testing to
stop the meter.

After it finishes, read all outputs into the backend env:

```bash
azd env get-values > /tmp/azd.env   # then copy the values you need into backend/.env
azd env get-values | grep -E 'FOUNDRY_|AZURE_'
```

> The Bicep schema is verified against the official Foundry sample
> (`microsoft-foundry/foundry-samples` `00-basic`), but it has **not** been
> compile-checked locally (no bicep CLI in the dev box). If `azd up` surfaces a
> Bicep error, that's the place to look first.
>
> **Endpoint form:** `FOUNDRY_PROJECT_ENDPOINT` is emitted as
> `https://<account>.services.ai.azure.com/api/projects/<project>`. If
> `FoundryChatClient` rejects it at runtime, try the account-only endpoint from
> the `AZURE_AI_ACCOUNT_ENDPOINT` output instead.

### 2. Backend env + knowledge base ingestion

```bash
cd backend
cp .env.example .env          # fill all values from `azd env get-values`
az login                      # identity that received the RBAC roles

# One-time data-plane objects (not provisioned by Bicep — same pattern for both):
uv run python -m app.knowledge.ingest      # build the Foundry IQ knowledge base
uv run python -m app.memory_provision      # create the Foundry memory store
```

Ingestion uploads the corpus to blob, creates the blob knowledge source (Azure
AI Search auto-chunks + embeds it), and creates the knowledge base. Indexing
takes a few minutes; the script polls until it settles. The memory store is a
Foundry data-plane object the per-user memory reads/writes into.

```bash
uv run uvicorn app.server:app --port 8000 --reload
```

Auth is always `DefaultAzureCredential` — `az login` / `azd auth login`, no keys.

### 3. Frontend

```bash
cd frontend
cp .env.example .env.local
npm install
npm run dev                   # http://localhost:3000
```

Open http://localhost:3000 and send a message — it round-trips
CopilotKit → `/api/copilotkit` → AG-UI (`:8000/helpdesk`) → Foundry.

## Acceptance

**Phase 0**
- 🟢 message round-trips with streaming visible in the CopilotKit chat.
- 🔴 CORS blocking, or `DefaultAzureCredential` failing locally.

**Phase 1** (ask about a runbook, e.g. *"VPN keeps dropping on my new laptop"*)
- 🟢 the answer cites a real corpus document; an off-corpus question (e.g.
  *"what's the capital of France?"*) returns "I don't know" instead of guessing.
- 🔴 empty retrieval, or an answer with no citation.

## Tear down (stop the cost)

```bash
azd down --purge     # deletes the resource group incl. AI Search (the hourly cost)
```

Next: Phase 2 (workflow + streaming of intermediate steps). See the spec's phase plan.
