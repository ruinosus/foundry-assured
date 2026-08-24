# Foundry Assured

**An internal engineering support assistant that proves what it tells you.**

Ask it a question and it answers from your own runbooks, showing the source of every
claim — and that source is one click away, not a name you have to take on faith. If the
answer requires *doing* something — opening a ticket, changing a resource — it stops and
asks a human first. It never invents a source, never shows you a document you are not
entitled to read, and never writes anything without approval. Those are not promises in
a README: each one is a test that fails the build when broken.

Built as a **Microsoft Foundry** showcase — knowledge base, multi-agent workflow,
per-user memory, human-in-the-loop approval, evaluation and tracing — with an
assurance layer on top. Frontend is **CopilotKit** (Next.js) over the **AG-UI**
protocol; backend is Python.

---

## What you actually get

Sign in with your Microsoft account and you land in a console with several assistants.

| Screen | What it is |
|---|---|
| `/d/helpdesk` | The support concierge — the full triage → retrieve → resolve → escalate workflow |
| `/d/selfwiki` | Cited Q&A over a wiki generated from **this repository's own code** |
| `/d/oncall` | Incident triage — the approver can **edit** the escalation before it fires, not just accept or decline it |
| `/d/deepcall` | The same incident-triage problem, on a second agent harness, to compare the two side by side |
| `/d/platform` | Ops concierge that calls Microsoft tools directly — Learn, Azure, Entra, DevOps, GitHub — with approval required before any write |
| `/tickets` | The tickets that were actually opened |
| `/evals` | Quality scores for the agent's answers |
| `/admin/users` | Users and role assignments (via Microsoft Graph) |

### What happens when you ask something

Type *"How do I recover my GitHub 2FA?"* into the helpdesk and you watch it work:

1. **Triage** — classifies intent and urgency.
2. **Retrieve** — searches the knowledge base, trimmed to what *you* are allowed to see.
3. **Resolve** — answers with at least one citation, e.g. *"open a ticket with the IT
   Identity team from a verified corp device [1]."* No source, no answer — it declines
   instead of guessing.
4. **Escalate** — if action is needed, an **approval card** appears. The ticket is
   created only after you approve it, and only if you hold the **Approver** role.
5. **Remember** — preferences and resolutions carry across sessions.

The intermediate steps stream to the screen as they happen. You are not staring at a
spinner waiting for a paragraph.

### Every citation opens the real document

The `[1]` in the answer above is a button. Click it and the source document opens
alongside the chat — full text, with the exact cited sentence highlighted so you don't
have to hunt for it in a multi-page runbook. That evidence sits under its own answer,
not in a side panel that only ever shows the last one, so it's still there when you
scroll back up through the conversation — and it's still there after you reload the
page.

Opening the document re-checks **your** access at the moment you click, not at the
moment the answer was written. If you're not entitled to that document, it doesn't
open — even though the citation appeared in the answer you can already see. This
applies to `helpdesk` and `selfwiki`, the two assistants that ground answers in
documents; `oncall`, `deepcall` and `platform` don't cite documents by design (incident
triage and tool calls, not retrieval).

The `platform` domain works differently in general: it does not search documents, it
**calls tools**. Read operations answer directly; every **write** goes behind human
approval with a required role per tool.

---

## Why "Assured"

Anyone can wire a chatbot to a vector store. The hard part is being able to say what it
will and will not do — and prove it. Every guarantee below is enforced by something that
turns CI red:

| Guarantee | How it is proved |
|---|---|
| Every answer cites a source | Policy gate that **plants a violation** and fails if it is not caught |
| Citations are checkable, not just claimed | Clicking a citation re-authorizes the document read for the signed-in caller |
| You only see what you may see | Per-document ACL applied **before** the model sees the content |
| No write without a human | Approval **plus** the Approver role, structurally — the ticket is created only in the response handler |
| The wiki does not lie about the code | Build-fidelity floor at 80%; the last measured run scored 85–98% per component ([case study](./docs/CASE-STUDY-SELFWIKI-DOGFOOD.md)) |

Read the method in [`docs/METHOD.md`](./docs/METHOD.md).

---

## The domain is swappable

The architecture is *"ask → ground → resolve → escalate."* Swapping the domain means
swapping the corpus and the prompts — the machinery does not change. The shipped corpus
is 13 generic engineering runbooks (2FA recovery, deploy rollback, pod crashloop, prod
credential rotation, incident severity…), which is enough to see it work and not enough
to be useful to your team. Making it yours: [`docs/CUSTOMIZE.md`](./docs/CUSTOMIZE.md).

There's also a machine-facing surface: `/mcp` exposes a `search_docs` tool over the same
access-controlled knowledge base, for MCP clients rather than the chat UI. It authenticates
as an Entra Resource Server — no client secret, just a bearer token the client obtains per
RFC 9728 — and every search is trimmed by the caller's own document ACL, same as the chat.

## Quickstart

```bash
azd auth login && az login
azd up                      # provision Azure infra
./scripts/setup-entra.sh    # optional: Entra sign-in + OBO (skip to run without auth)
./scripts/bootstrap.sh      # fill .env, ingest the knowledge base, provision memory

cd apps/backend  && uv run uvicorn app.main:app --port 8000 --reload
cd apps/frontend && npm install && npm run dev      # http://localhost:3000
```

Full runbook + the manual steps behind the scripts: [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md).
Cost and teardown: [`docs/COST.md`](./docs/COST.md).

## Demo mode — see it with **no Azure**

Want to see the experience before provisioning anything? Committed AG-UI fixtures are
replayed by CopilotKit's **aimock** — the real frontend renders the real flow
(triage→retrieve→resolve **steps**, grounded **cited** answers, honest off-corpus
decline) with **no Azure and no Python backend**:

```bash
cd apps/frontend && npm install && npm run demo      # → http://localhost:3000
```

The fixtures are **recorded from real runs** (`./scripts/demo-record.sh`), so they're
genuine workflow output, not hand-faked — just replayed deterministically. Try the
recorded prompts: *"How do I roll back a bad deploy?"*, *"My Kubernetes pod is stuck in
CrashLoopBackOff…"*, *"What's the weather in Paris?"* (off-corpus → declines).

> The **HITL ticket approval** isn't in the fixture yet (the resume handshake is
> captured by recording through the live UI); it runs in the full app. Add it by
> re-recording with `./scripts/demo-record.sh` and approving a ticket in the browser.

## Documentation

|  |  |
|---|---|
| [`docs/METHOD.md`](./docs/METHOD.md) | the assurance mechanism — how each guarantee is measured and run |
| [`docs/DEPLOYMENT.md`](./docs/DEPLOYMENT.md) | clone → provision → deploy, step by step |
| [`docs/CUSTOMIZE.md`](./docs/CUSTOMIZE.md) | swap the corpus, prompts and action for your own domain |
| [`docs/COST.md`](./docs/COST.md) | what each Azure resource costs, and how to tear it down |
| [`docs/OBSERVABILITY.md`](./docs/OBSERVABILITY.md) | what telemetry is emitted, and what is deliberately not |
| [`docs/RBAC-AND-USER-MANAGEMENT-PLAN.md`](./docs/RBAC-AND-USER-MANAGEMENT-PLAN.md) | the four app roles and who can approve what |
| [`docs/adr/`](./docs/adr/) | the architecture decisions, with the measurements behind them |
| [`CLAUDE.md`](./CLAUDE.md) · [`CONTRIBUTING.md`](./CONTRIBUTING.md) · [`SECURITY.md`](./SECURITY.md) | repository layout, contribution workflow, and security policy |

## References

- Agent Framework evaluation — learn.microsoft.com/agent-framework/agents/evaluation
- Deploy a hosted agent — learn.microsoft.com/azure/foundry/agents/how-to/deploy-hosted-agent
- agent-framework hosting samples — github.com/microsoft/agent-framework `python/samples/04-hosting/foundry-hosted-agents`
- AG-UI ↔ Agent Framework — learn.microsoft.com/agent-framework/integrations/ag-ui/
