# Runbook: Local development environment setup

**Applies to:** Setting up a backend service for local development.

## Prerequisites
- Python managed with `uv`, Node 22 LTS, Docker Desktop, and the corp VPN for any service that talks to internal APIs.

## Steps
1. Clone the repo and run `uv sync` in the service directory.
2. Copy `.env.example` to `.env` and fill in the values from your team's onboarding doc.
3. Start dependencies with `docker compose up -d` (Postgres, Redis).
4. Run database migrations: `uv run alembic upgrade head`.
5. Start the service: `uv run uvicorn app.server:app --reload`.

## Common issues
- **Port already in use:** another process holds the port. Find it with `lsof -i :8000` and stop it.
- **Auth errors against Azure:** run `az login` so `DefaultAzureCredential` can pick up your identity.
- **Schema drift:** if migrations fail, reset the local DB volume and re-run `alembic upgrade head`.
