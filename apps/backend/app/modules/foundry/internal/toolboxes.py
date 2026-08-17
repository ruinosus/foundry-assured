"""Toolbox — o que junta tools e skills num pacote que o agente alcança.

ISTO ESTAVA FALTANDO, e a falta tornava skill decorativa. O levantamento (feito depois de a
pergunta certa ser feita) mostrou o modelo do Foundry:

    ToolboxVersionObject → { tools: [ToolboxTool], skills: [ToolboxSkillReference], policies }

Ou seja: **skill não entra em `PromptAgentDefinition.tools`**. Uma skill só chega a um agente
passando por um toolbox. Tools (MCP, Azure AI Search, Code Interpreter, Web Search…) entram nos
dois lugares — direto no agente OU no toolbox — mas skill, só aqui.

`ToolboxSkillReference` referencia por NOME e opcionalmente VERSÃO. Sem versão, o serviço usa a
`default_version` da skill — que é exatamente por que a listagem de skills mostra `default` e
`latest` lado a lado: publicar versão nova não muda o que o toolbox entrega se a default não
acompanhar.

O QUE NÃO CONSEGUI DETERMINAR, e prefiro declarar a chutar: no SDK instalado não achei o campo
que amarra um agente a um toolbox NOMEADO. Existe `ToolSearchToolParam` (type `tool_search`) do
lado do agente, com `execution: server | client`, mas ele não aponta para um toolbox específico.
Ou o vínculo é resolvido no nível do projeto, ou está em superfície que esta versão do SDK Python
ainda não expõe. Até isso ser confirmado contra a documentação, a tela mostra o toolbox como
catálogo — e NÃO promete um botão "usar este toolbox neste agente" que eu não sei implementar.

Verificado contra o SDK INSTALADO (RULE #1): `ToolboxesOperations` (8 operações),
`ToolboxVersionObject`, `ToolboxSkillReference`.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.modules.foundry.internal.names import qualify


class InvalidToolbox(ValueError):
    """Pedido de toolbox que não vira recurso, com o motivo."""


def _client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    from app.modules.tenancy.public import tenant_config

    return AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _project(obj: Any) -> dict:
    """Um toolbox na forma que a interface consome."""
    default = getattr(obj, "default_version", None)
    return {
        "name": getattr(obj, "name", None),
        "id": getattr(obj, "id", None),
        "default_version": getattr(default, "version", None) if default else None,
    }


def _project_version(v: Any) -> dict:
    """Uma versão de toolbox: o que ela CONTÉM é a informação que importa."""
    tools = getattr(v, "tools", None) or []
    skills = getattr(v, "skills", None) or []
    return {
        "version": getattr(v, "version", None),
        "description": getattr(v, "description", None),
        "created_at": _iso(getattr(v, "created_at", None)),
        # `type` é o discriminador do serviço (mcp, azure_ai_search, code_interpreter…): não se
        # traduz, é o que a pessoa procura na documentação.
        "tools": [
            {
                "type": str(getattr(t, "type", "") or "") or None,
                "name": getattr(t, "name", None),
                "description": getattr(t, "description", None),
            }
            for t in tools
        ],
        # Sem `version`, o serviço usa a default da skill — e a listagem de skills é onde se vê
        # se a default está atrás da mais recente.
        "skills": [
            {"name": getattr(s, "name", None), "version": getattr(s, "version", None)}
            for s in skills
        ],
    }


def list_toolboxes(limit: int = 50) -> list[dict]:
    client = _client()
    try:
        out: list[dict] = []
        for item in client.toolboxes.list(limit=min(limit, 100)):
            out.append(_project(item))
            if len(out) >= limit:
                break
        return out
    finally:
        with contextlib.suppress(Exception):
            client.close()


def get_toolbox(name: str) -> dict:
    """Um toolbox com o conteúdo da versão default — tools e skills que ele entrega."""
    client = _client()
    try:
        out = _project(client.toolboxes.get(name))
        with contextlib.suppress(Exception):
            versions = list(client.toolboxes.list_versions(name))
            out["versions"] = [_project_version(v) for v in versions]
        return out
    finally:
        with contextlib.suppress(Exception):
            client.close()


def parse_toolbox(body: dict) -> dict:
    """Valida o pedido e devolve tools e referências de skill, como dados.

    Offline-testável de propósito: nada aqui importa `azure.ai.projects`.
    """
    if not isinstance(body, dict):
        raise InvalidToolbox("O pedido precisa ser um objeto (mapa de chaves).")

    tools = body.get("tools") or []
    if not isinstance(tools, list):
        raise InvalidToolbox("`tools` deve ser uma lista.")

    raw_skills = body.get("skills") or []
    if not isinstance(raw_skills, list):
        raise InvalidToolbox("`skills` deve ser uma lista de nomes ou de {name, version}.")

    skills = []
    for s in raw_skills:
        if isinstance(s, str):
            skills.append({"name": s})
        elif isinstance(s, dict) and s.get("name"):
            ref = {"name": s["name"]}
            if s.get("version"):
                ref["version"] = str(s["version"])
            skills.append(ref)
        else:
            raise InvalidToolbox(
                "Cada skill deve ser um nome, ou {name, version} com o nome preenchido."
            )

    if not tools and not skills:
        raise InvalidToolbox("Um toolbox vazio não entrega nada — inclua ao menos uma tool ou skill.")

    return {"tools": tools, "skills": skills}


def create_toolbox_version(name: str, body: dict) -> dict:
    """Publica uma versão do toolbox com as tools e as skills informadas."""
    from azure.ai.projects.models import ToolboxSkillReference

    parsed = parse_toolbox(body)
    qualified = qualify(name)

    client = _client()
    try:
        version = client.toolboxes.create_version(
            qualified,
            tools=parsed["tools"],
            skills=[
                ToolboxSkillReference(name=s["name"], version=s.get("version"))
                for s in parsed["skills"]
            ]
            or None,
            description=str(body.get("description") or "") or None,
        )
        return {
            "name": qualified,
            "version": getattr(version, "version", None),
            "tools": len(parsed["tools"]),
            "skills": len(parsed["skills"]),
        }
    finally:
        with contextlib.suppress(Exception):
            client.close()


def delete_toolbox(name: str) -> dict:
    qualified = qualify(name)
    client = _client()
    try:
        client.toolboxes.delete(qualified)
        return {"name": qualified, "deleted": True}
    finally:
        with contextlib.suppress(Exception):
            client.close()
