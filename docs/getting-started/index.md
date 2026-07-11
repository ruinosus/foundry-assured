---
title: Getting started
description: Bring up Foundry Assured locally and run your first grounded helpdesk flow — demo mode (no Azure) or end-to-end.
type: tutorial
audience: adopter
status: stable
updated: 2026-07-11
---

# Getting started

By the end of this tutorial you'll have the Assurance Console open in your browser and a
grounded, cited answer streaming back from the helpdesk concierge. Two paths: **demo mode**
(no Azure, no cost — the fastest way to *see* it) and the **full stack** (against your own
Microsoft Foundry project).

## Prerequisites

- **Node.js 20+** and **npm** (the Next.js frontend).
- **Python 3.12** and **[uv](https://docs.astral.sh/uv/)** (the FastAPI backend).
- For the full stack only: an Azure subscription, the **Azure Developer CLI (`azd`)** and the
  **Azure CLI (`az`)**, and a region where `gpt-5-mini` GlobalStandard is available.

Clone the repo and check out the integration branch:

```bash
git clone https://github.com/ruinosus/foundry-assured.git
cd foundry-assured
git checkout develop
```

## Path A — demo mode (no Azure)

Recorded AG-UI fixtures are replayed by [CopilotKit **aimock**](https://github.com/CopilotKit/aimock),
so the *real* frontend renders the *real* flow — triage → retrieve → resolve **steps**, grounded
**cited** answers, an honest off-corpus decline — with no Python backend and no cloud.

```bash
cd apps/frontend
npm install
npm run demo          # → http://localhost:3000
```

Open <http://localhost:3000> and try the recorded prompts:

- *"How do I roll back a bad deploy?"* — a grounded answer with a runbook citation.
- *"My Kubernetes pod is stuck in CrashLoopBackOff…"* — the multi-step workflow.
- *"What's the weather in Paris?"* — **off-corpus → the agent declines** (the assurance
  mechanism at work: no source, no answer).

The fixtures are recorded from real runs (`./scripts/demo-record.sh`), so it's genuine
workflow output replayed deterministically — not hand-faked.

## Path B — full stack (against Foundry)

### 1. Provision Foundry

```bash
azd auth login && az login
azd up          # prompts for env name + location; provisions everything in infra/
```

This creates the resource group, the Foundry account + project, a `gpt-5-mini` +
`text-embedding-3-small` deployment, Azure AI Search, Storage, an ACR, and keyless RBAC.

### 2. Backend + data-plane objects

```bash
cd apps/backend
cp .env.example .env                    # fill from `azd env get-values`
uv sync
uv run python -m app.knowledge.ingest   # build the Foundry IQ knowledge base
uv run python -m cli.provision_memory   # create the memory store
uv run uvicorn app.main:app --port 8000 --reload
```

The knowledge base and memory store are **data-plane** objects created by scripts (Bicep is
control-plane only). Auth is always `DefaultAzureCredential` — no keys.

### 3. Frontend

```bash
cd apps/frontend
cp .env.example .env.local              # NEXT_PUBLIC_ENTRA_* for sign-in (optional)
npm install
npm run dev                             # → http://localhost:3000
```

Open <http://localhost:3000> → the Overview, then **`/d/helpdesk`** for the console. Ask
*"How do I roll back a bad deploy?"* and watch the **triage → retrieve → resolve** steps stream
in, with an **EvidencePanel** showing the runbook the answer cited and its assurance badges.

> [!TIP]
> Unset `NEXT_PUBLIC_ENTRA_*` and the app boots without sign-in (falls back to
> `DefaultAzureCredential`). Set them to gate behind Microsoft sign-in and call Foundry
> **on-behalf-of** the signed-in developer. See [Identity & access](../IDENTITY-AND-ACCESS-SETUP.md).

## Where to next

- **[Deploy from zero](../DEPLOYMENT.md)** — the full provisioning runbook (infra, Entra,
  KB/memory, hosted agent, Container Apps).
- **[Swap in your own domain](../CUSTOMIZE.md)** — turn this into any "ask → ground → resolve →
  escalate" assistant.
- **[Architecture](../reference/architecture.md)** — how the domains, agents and flow fit together.
- **[The assurance mechanism](../METHOD.md)** — what the measured gates actually guarantee.
