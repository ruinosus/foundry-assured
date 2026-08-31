"""Recursos do Foundry expostos ao usuário final.

Este módulo existe pela frase que define o produto: *preencher lacunas e trazer outros perfis
de usuário para consumir recursos Microsoft*. O portal do Foundry atende quem tem RBAC no
Azure; aqui a mesma capacidade chega a quem não tem e não vai ter.

Por isso o módulo é fino por construção: a gestão está no SDK (45 operações entre
`AgentsOperations` e as de knowledge no `SearchIndexClient`), e o que escrevemos é projeção,
validação e autorização.

A ÚNICA exceção é `ingest_repo`: não existe knowledge source de GitHub em primeira parte, e as
três alternativas plausíveis falham — o conector do Logic Apps lê issues e PRs, não a árvore de
arquivos; `WebKnowledgeSource` é Bing público; a galeria de data sources não tem GitHub. Ela lê
os arquivos e escreve no blob, e do blob em diante volta a ser oficial.
"""

from app.modules.foundry.internal.agent_write import (
    create_agent_version,
    delete_agent,
    set_agent_enabled,
)
from app.modules.foundry.internal.agents import get_agent, list_agents
from app.modules.foundry.internal.assist import suggest
from app.modules.foundry.internal.chat import chat_client, set_chat_middleware
from app.modules.foundry.internal.flow_store import load_flow, save_flow
from app.modules.foundry.internal.github_source import ingest_repo
from app.modules.foundry.internal.knowledge_catalog import get_knowledge, list_knowledge
from app.modules.foundry.internal.knowledge_write import (
    create_knowledge,
    delete_knowledge,
    upload_files,
)
from app.modules.foundry.internal.names import qualify as qualify_agent_name
from app.modules.foundry.internal.skill_catalog import (
    KNOWN_CATALOGS,
    import_skill,
    list_catalog,
    preview_skill,
)
from app.modules.foundry.internal.skills import (
    create_skill,
    create_skill_from_files,
    delete_skill,
    get_skill,
    list_skills,
)
from app.modules.foundry.internal.toolboxes import (
    create_toolbox_version,
    delete_toolbox,
    get_toolbox,
    list_toolbox_projection,
    list_toolboxes,
    mcp_url,
    resolve_toolbox_default_version,
    resolve_toolbox_version,
)

__all__ = [
    "KNOWN_CATALOGS",
    "chat_client",
    "create_agent_version",
    "create_knowledge",
    "create_skill",
    "create_skill_from_files",
    "create_toolbox_version",
    "delete_agent",
    "delete_knowledge",
    "delete_skill",
    "delete_toolbox",
    "get_agent",
    "get_knowledge",
    "get_skill",
    "get_toolbox",
    "import_skill",
    "ingest_repo",
    "list_agents",
    "list_catalog",
    "list_knowledge",
    "list_skills",
    "list_toolbox_projection",
    "list_toolboxes",
    "load_flow",
    "mcp_url",
    "preview_skill",
    "qualify_agent_name",
    "resolve_toolbox_default_version",
    "resolve_toolbox_version",
    "save_flow",
    "set_agent_enabled",
    "set_chat_middleware",
    "suggest",
    "upload_files",
]
