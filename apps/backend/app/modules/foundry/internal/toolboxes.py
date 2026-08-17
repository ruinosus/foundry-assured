"""Toolbox — o que junta tools e skills num pacote que o agente alcança.

ISTO ESTAVA FALTANDO, e a falta tornava skill decorativa. O modelo do Foundry:

    ToolboxVersionObject → { tools: [ToolboxTool], skills: [ToolboxSkillReference], policies }

Ou seja: **skill não entra em `PromptAgentDefinition.tools`**. Uma skill só chega a um agente
passando por um toolbox. Tools (MCP, Azure AI Search, Code Interpreter, Web Search…) entram nos
dois lugares — direto no agente OU no toolbox — mas skill, só aqui.

`ToolboxSkillReference` referencia por NOME e opcionalmente VERSÃO. Sem versão, o serviço usa a
`default_version` da skill — que é exatamente por que a listagem de skills mostra `default` e
`latest` lado a lado: publicar versão nova não muda o que o toolbox entrega se a default não
acompanhar.

COMO O AGENTE ALCANÇA UM TOOLBOX — respondido pela documentação, depois de o SDK não responder:
**o toolbox É um servidor MCP.** Não existe campo `toolbox_id` no agente, e não falta nada no SDK:
o vínculo é a URL. O agente recebe um `mcp` tool comum apontando para

    {project_endpoint}/toolboxes/{nome}/mcp?api-version=v1

O endpoint *consumer* (sem versão no caminho) serve sempre a `default_version` — por isso promover
uma skill é rollout sem tocar em código de agente nem no toolbox. Há também o endpoint
*developer*, com a versão explícita, para testar antes de promover.

Skills dentro do toolbox aparecem como **MCP Resources** (`skill://{nome}`), descobertas por
`resources/list`.

VERIFICADO EMPIRICAMENTE, em três rodadas, e cada erro moveu o problema um passo adiante:

  1. sem connection → `401 PermissionDenied` ao conectar no endpoint;
  2. com connection malformada (`authType: AAD`, api-version GA) → `Connection resolution failed`;
  3. com a connection correta e um toolbox só de skills →
     `McpProtocolException: List of tool configs not provided in _meta.tools`;
  4. com a connection correta e um toolbox COM tool → **o agente conectou, enumerou e respondeu.**

`ensure_toolbox_connection` cria a connection automaticamente na publicação, então nada disso
recai sobre quem usa o produto.

O QUE A RODADA 4 RESPONDEU, e é a conclusão que faltava: o agente respondeu, mas **NÃO soube o
conteúdo da skill** que estava no toolbox. Ou seja — o `mcp` tool server-side do Foundry enumera
as TOOLS do toolbox e as usa; as SKILLS, que chegam como MCP Resources (`resources/list`), NÃO são
lidas por um PromptAgent. A hipótese levantada na pesquisa se confirmou no teste.

CONSEQUÊNCIA PRÁTICA:
  * toolbox como fonte de TOOLS para um agente do Foundry: funciona;
  * skill chegando a um agente do Foundry por essa via: não funciona;
  * para skill, o caminho é **direct injection** — `GET /skills/{nome}/content` devolve um ZIP, o
    runtime lê o `SKILL.md` no startup e injeta como instrução da sessão. Funciona sem toolbox, e
    é o mesmo modelo da ADR-013/014 deste repositório. Vale para os agentes que rodam no NOSSO
    backend, que é onde o produto tem controle do runtime.

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
        # A connection nasce junto com o toolbox: sem ela o agente que o usar recebe 401 na
        # primeira chamada, e o usuário final não deveria precisar saber o que é uma connection.
        # Falha aqui NÃO desfaz o toolbox — ele é válido e utilizável por cliente MCP autenticado
        # de outra forma; o que se perde é o atalho. Por isso o motivo sobe na resposta em vez de
        # virar exceção.
        conn: str | None = None
        conn_error: str | None = None
        try:
            from app.modules.foundry.internal.connections import (
                ensure_toolbox_connection,
            )

            info = mcp_url(name)
            conn = ensure_toolbox_connection(qualified, info["url"])["name"]
        except Exception as exc:  # noqa: BLE001 — o toolbox vale mais que o atalho
            conn_error = str(exc)

        return {
            "name": qualified,
            "version": getattr(version, "version", None),
            "tools": len(parsed["tools"]),
            "skills": len(parsed["skills"]),
            "connection": conn,
            "connection_error": conn_error,
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


def mcp_url(name: str, version: str = "", *, connection: str | None = None) -> dict:
    """A URL MCP deste toolbox — o que liga um agente a ele.

    Duas variantes, e a diferença é operacional:

      * **consumer** (sem versão): serve sempre a `default_version`. É a que se usa em agente de
        produção, porque promover uma versão nova passa a valer sem tocar no agente.
      * **developer** (com versão): fixa uma versão, para testar antes de promover.

    Devolve também o corpo pronto do `mcp` tool, porque montá-lo à mão é exatamente o tipo de
    coisa que este produto existe para evitar: quem sabe escrever esse JSON não precisa da tela.
    """
    from app.modules.tenancy.public import tenant_config

    qualified = qualify(name)
    endpoint = (tenant_config().foundry_project_endpoint or "").rstrip("/")
    path = (
        f"{endpoint}/toolboxes/{qualified}/versions/{version}/mcp?api-version=v1"
        if version
        else f"{endpoint}/toolboxes/{qualified}/mcp?api-version=v1"
    )
    tool = {
        "type": "mcp",
        "server_label": qualified.replace("-", "_"),
        "server_url": path,
        # A doc é explícita: o endpoint do toolbox NÃO bloqueia `tools/call`. Este campo é
        # declaração que o runtime do agente precisa honrar — não é gate do serviço. Mantê-lo em
        # "always" é o default seguro, e o aviso está aqui para ninguém confundir os dois.
        "require_approval": "always",
    }
    # A connection é o que faz o agente autenticar no endpoint. Sem ela: 401 na primeira chamada.
    if connection:
        tool["project_connection_id"] = connection
    return {
        "name": qualified,
        "version": version or None,
        "url": path,
        "connection": connection,
        "tool": tool,
    }
