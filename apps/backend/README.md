# Foundry Helpdesk — backend

FastAPI + Microsoft Agent Framework, exposing the helpdesk agent over AG-UI.

```bash
uv sync
cp .env.example .env
uv run uvicorn app.main:app --port 8000 --reload
```

Auth is always `DefaultAzureCredential`. See the root [README](../README.md) and
[CLAUDE.md](../CLAUDE.md).
