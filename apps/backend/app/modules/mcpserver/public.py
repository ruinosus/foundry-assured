"""Superfície do módulo mcpserver. Único ponto importável de fora (ADR-017).

Este módulo NÃO implementa capacidade nenhuma. Ele traduz o que outros módulos já expõem
(`knowledge.public`, `app.shared.auth`) para o vocabulário MCP. Se alguém escrever aqui uma
regra de acesso, uma consulta ou um prompt, o PR está errado: essas coisas têm dono, e o dono
não é este módulo.
"""

from __future__ import annotations

from app.modules.mcpserver.internal.server import MOUNT_PATH
from app.modules.mcpserver.internal.server import build_app as build_mcp_app
from app.modules.mcpserver.internal.tools_knowledge import set_domain_registry

__all__ = ["MOUNT_PATH", "build_mcp_app", "set_domain_registry"]
