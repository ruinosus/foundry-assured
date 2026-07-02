# Hosted-platform container (built remotely by ACR — remoteBuild: true in azure.yaml).
# Mirrors the official agent-framework foundry-hosted-agents sample. Serves the
# Invocations protocol on 8088 via InvocationsHostServer (started by main.py).
FROM python:3.12-slim

WORKDIR /app

COPY . user_agent/
WORKDIR /app/user_agent

RUN if [ -f requirements.txt ]; then \
        pip install --no-cache-dir -r requirements.txt; \
    else \
        echo "No requirements.txt found"; \
    fi

EXPOSE 8088

CMD ["python", "main.py"]
