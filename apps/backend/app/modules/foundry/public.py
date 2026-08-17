"""Recursos do Foundry expostos ao usuário final.

Este módulo existe pela frase que define o produto: *preencher lacunas e trazer outros perfis
de usuário para consumir recursos Microsoft*. O portal do Foundry atende quem tem RBAC no
Azure; aqui a mesma capacidade chega a quem não tem e não vai ter.

Por isso o módulo é fino por construção: a gestão está no SDK (`AgentsOperations` e os grupos
vizinhos), e o que escrevemos é projeção e autorização.
"""

from app.modules.foundry.internal.agents import get_agent, list_agents
from app.modules.foundry.internal.knowledge_catalog import get_knowledge, list_knowledge

__all__ = ["get_agent", "get_knowledge", "list_agents", "list_knowledge"]
