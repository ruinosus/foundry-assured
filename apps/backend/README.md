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

Auth is always `DefaultAzureCredential` (Foundry/KB/memory); user requests carry an
Entra token (OBO + the `roles` claim). See the root [README](../README.md) and
[CLAUDE.md](../CLAUDE.md).
