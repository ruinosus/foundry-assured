# Backend container (Azure Container Apps). FastAPI + AG-UI on :8000.
# Built/pushed by azd; runs as the app's managed identity (DefaultAzureCredential
# picks it up) — for OBO the Entra API client id/secret come from env.
FROM python:3.12-slim

WORKDIR /app

# uv for reproducible installs from the lockfile.
RUN pip install --no-cache-dir uv

# Dependencies first (cached), then the app code.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app

ENV PATH="/app/.venv/bin:$PATH"
EXPOSE 8000

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
