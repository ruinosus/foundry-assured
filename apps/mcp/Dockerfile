# Container do servidor MCP (Azure Container Apps). FastMCP 4 sobre :8001.
# Roda como a managed identity do app (o `DefaultAzureCredential` a encontra) — nenhum segredo
# entra aqui (ADR-005); o token do chamador é o que decide o que ele lê.
#
# O CONTEXTO DE BUILD É A RAIZ DO REPOSITÓRIO, não `apps/mcp`:
#
#     docker build -f apps/mcp/Dockerfile -t foundry-assured-mcp .
#
# `apps/mcp` depende de `apps/backend` por path (`[tool.uv.sources]`), então os dois precisam
# estar no contexto. Buildar de dentro de `apps/mcp` falha em `uv sync` com o diretório
# `../backend` inexistente — falha alta, no build, que é o melhor lugar para ela acontecer.
FROM python:3.12-slim

WORKDIR /srv

RUN pip install --no-cache-dir uv

# O pacote do backend precisa estar presente ANTES do `uv sync`, porque é dependência por path
# e o uv o constrói a partir da árvore. Só os arquivos que o wheel dele usa.
COPY apps/backend/pyproject.toml apps/backend/README.md ./backend/
COPY apps/backend/app ./backend/app
COPY apps/backend/agents ./backend/agents

WORKDIR /srv/mcp
COPY apps/mcp/pyproject.toml apps/mcp/uv.lock ./

# SEM `--extra agents`, e é o ponto inteiro deste app (ADR-027): a base do backend instala sem
# `agent-framework[all]`, o que libera o teto `mcp<2` e deixa o FastMCP 4 (que exige `mcp>=2`)
# caber no mesmo venv. Acrescentar o extra aqui faria o `uv sync` falhar a resolução — falha
# alta, não silenciosa.
RUN uv sync --frozen --no-dev --no-install-project

COPY apps/mcp/mcp_app ./mcp_app

ENV PATH="/srv/mcp/.venv/bin:$PATH"
EXPOSE 8001

CMD ["uvicorn", "mcp_app.main:app", "--host", "0.0.0.0", "--port", "8001"]
