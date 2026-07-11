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

### Container run — prompt edits without a rebuild (ADR-014)

`compose.yaml` runs the same image the deploy uses, but bind-mounts the
working-tree DNA scope over the baked-in copy, so editing a prompt YAML needs
a **restart, not a rebuild**:

```bash
docker compose up -d                       # build once, run
$EDITOR .dna/helpdesk/agents/cockpit.yaml  # change a prompt
docker compose restart backend             # restart picks it up — no image build
```

Prompts compose at import (`app/agents/prompts.py`) and agents are built at
boot, so a restart is the refresh unit — see
[ADR-014](../../docs/adr/ADR-014-runtime-prompt-scope-no-rebuild.md).

In **production** (azd/ACA) the same loop goes through an Azure Files share
mounted read-only at `/mnt/dna` and selected via `DNA_BASE_DIR` (ADR-014,
production leg). Publish with:

```bash
$EDITOR .dna/helpdesk/agents/cockpit.yaml           # change a prompt
dna eval run helpdesk-prompts --scope helpdesk      # content gate (CI runs it too)
../../scripts/push-prompts.sh                       # upload + revision restart — no image build
```

Set `DNA_BASE_DIR` to point the backend at any external scope directory: if
`$DNA_BASE_DIR/helpdesk` exists it wins (and a broken scope fails the boot
loudly); if it is absent (empty/unseeded share) the backend logs a warning and
falls back to the copy baked into the image, so a fresh provision never
crash-loops. Unset means the baked-in copy, byte-identical to before.

Auth is always `DefaultAzureCredential` (Foundry/KB/memory); user requests carry an
Entra token (OBO + the `roles` claim). See the root [README](../README.md) and
[CLAUDE.md](../CLAUDE.md).
