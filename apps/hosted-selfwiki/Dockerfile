# Hosted-agent container (built remotely by ACR — remoteBuild: true in azure.yaml).
# Mirrors the official agent-framework foundry-hosted-agents sample. Serves the
# Responses protocol on 8088 via ResponsesHostServer (started by main.py).
FROM python:3.12-slim

WORKDIR /app

# NOTE: the build context includes the baked helpdesk DNA scope at ./.dna
# (a gitignored build artifact synced from apps/backend/.dna by the azd
# prepackage hook, scripts/sync-hosted-scope.sh). prompts.py composes the
# agent instruction from it at import — no inline prompt copy (ADR-013).
COPY . user_agent/
WORKDIR /app/user_agent

RUN if [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        echo "No requirements.txt found"; \
    fi

EXPOSE 8088

CMD ["python", "main.py"]
