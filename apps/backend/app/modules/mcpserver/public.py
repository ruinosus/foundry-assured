"""Superfície do módulo mcpserver. Único ponto importável de fora (ADR-017).

Este módulo NÃO implementa capacidade nenhuma. Ele traduz o que outros módulos já expõem
(`knowledge.public`, `app.shared.auth`) para o vocabulário MCP. Se alguém escrever aqui uma
regra de acesso, uma consulta ou um prompt, o PR está errado: essas coisas têm dono, e o dono
não é este módulo.
"""

from __future__ import annotations

__all__: list[str] = []
