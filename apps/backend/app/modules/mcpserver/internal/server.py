"""Constrói o FastMCP e devolve a aplicação ASGI que o `main.py` monta.

CORS: o `main.py` aplica `CORSMiddleware` no app inteiro, e a documentação do FastMCP avisa que
isso quebra as rotas `.well-known` e as requisições `OPTIONS` de um MCP autenticado montado em
prefixo. O padrão documentado é sub-app com middleware próprio — é por isso que o CORS do MCP
entra AQUI, via `http_app(middleware=...)`, e não lá.
"""

from __future__ import annotations

from fastmcp import FastMCP
from starlette.middleware import Middleware
from starlette.middleware.cors import CORSMiddleware
from starlette.types import ASGIApp

from app.modules.mcpserver.internal.auth import build_auth
from app.shared.settings import settings

INSTRUCTIONS = (
    "Assistente de engenharia com garantias: a busca respeita o controle de acesso por "
    "documento do chamador e toda resposta traz as fontes que a sustentam."
)


def build_mcp(base_url: str) -> FastMCP:
    from app.modules.mcpserver.internal import tools_knowledge

    mcp = FastMCP(
        "Foundry Assured",
        instructions=INSTRUCTIONS,
        auth=build_auth(base_url),
    )
    tools_knowledge.register(mcp)
    return mcp


def build_app(base_url: str) -> ASGIApp:
    mcp = build_mcp(base_url)
    return mcp.http_app(
        path="/",
        middleware=[
            Middleware(
                CORSMiddleware,
                allow_origins=[settings.frontend_origin],
                allow_methods=["*"],
                allow_headers=["*"],
            )
        ],
    )
