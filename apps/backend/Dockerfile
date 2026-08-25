# Backend container (Azure Container Apps). FastAPI + AG-UI on :8000.
# Built/pushed by azd; runs as the app's managed identity (DefaultAzureCredential
# picks it up) — for OBO the Entra API client id/secret come from env.
FROM python:3.12-slim

WORKDIR /app

# uv for reproducible installs from the lockfile.
RUN pip install --no-cache-dir uv

# Dependencies first (cached), then the app code.
COPY pyproject.toml uv.lock ./
# `--no-dev` skips the `dev` group — which is also where the `agents` extra rides for local
# `uv sync` ergonomics (see the comment on `[dependency-groups] dev` in pyproject.toml, and
# `[project.optional-dependencies] agents` for the why). A production image needs the runtime
# framework without the dev tooling, so it asks for the extra explicitly instead.
RUN uv sync --frozen --no-dev --no-install-project --extra agents

COPY app ./app
# Declarative agent definitions — AgentSchema documents (ADR-013/ADR-015),
# composed by app/agents/prompts.py at import. This baked-in copy keeps the image
# self-contained AND is the fallback when the external directory is absent.
# No-rebuild prompt edits (ADR-014): local compose bind-mounts the working-tree
# agents/ over this path; production (ACA) mounts an Azure Files share at
# /mnt/agents selected via AGENTS_DIR (scripts/push-prompts.sh).
COPY agents ./agents
# O modelo de valor (fórmula de retorno + procedência das constantes). Mesma lógica do `agents`
# acima: cópia baked no imagem, e `VALUE_MODEL` aponta para outro arquivo quando a instalação tem
# o seu. Esquecer esta linha derrubaria o painel de resultados no container e passaria despercebido
# em dev — foi assim que o corpus da KB ficou meses fora da imagem antes da ADR-017.
COPY value ./value

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
