"""Criar versão de agente, habilitar, desabilitar, apagar — via SDK oficial.

A SPEC ESTAVA ERRADA NUM PONTO, e o levantamento do SDK instalado corrigiu. Ela dizia que
"criar agente" seria `create_version_from_manifest`, tratando manifesto como documento enviado.
Não é: a assinatura real é

    create_version_from_manifest(agent_name, *, manifest_id: str, parameter_values: dict)

`manifest_id` é uma REFERÊNCIA a um manifesto já registrado no serviço, com parâmetros para
materializar. Serve para catálogo de templates, não para "traga seu YAML".

O caminho para definição enviada pelo usuário é `create_version(agent_name, definition=...)` com
`PromptAgentDefinition(kind, model, instructions, tools, temperature, top_p)` — campos verificados
no pacote instalado.

ISSO CAIU BEM, porque o formato que o usuário envia pode ser o MESMO que este repositório já usa
para seus próprios agentes: o documento AgentSchema da ADR-013 (`agents/helpdesk/*.yaml`), que
tem exatamente `model` e `instructions`. Então "criar agente" não inventa um formato nosso — usa
o que já é o padrão aqui, e a tradução para `PromptAgentDefinition` é o mapeamento de dois campos.

PowerFx (`=Env.X`) é RECUSADO no load, igual ao reader de prompts do repo: sem runtime .NET o
valor voltaria como string literal, e um agente com `=Env.MODEL` no lugar do modelo falha na
primeira chamada com erro que não aponta para a causa.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.modules.foundry.internal.names import qualify

# Campos com equivalente direto em `PromptAgentDefinition`, repassados como vêm.
#
# São TODOS os campos que o tipo aceita, menos `model` e `instructions` (obrigatórios, tratados
# à parte) e `kind` (é o próprio objeto). Antes eram só `temperature` e `top_p`, e a diferença
# importa: sem `tools` o agente criado não alcança nada — nem a base de conhecimento que o
# usuário acabou de criar na tela vizinha. O produto tinha as duas metades e nenhuma ponte.
_PASSTHROUGH = (
    "temperature",
    "top_p",
    "tools",
    "tool_choice",
    "reasoning",
    "text",
    "structured_inputs",
)

# Atalho de alto nível: `knowledge_base: <nome>` no documento vira o `AzureAISearchTool` completo.
#
# É a única conveniência nossa aqui, e existe porque a alternativa é pedir ao usuário final que
# escreva à mão a forma de `AzureAISearchTool(azure_ai_search=AzureAISearchToolResource(
# indexes=[AzureAISearchIndex(index_name=..., connection_name=...)]))`. Quem sabe montar isso não
# precisa deste produto; quem precisa deste produto não sabe. `tools` continua aceito cru para
# quem quiser controle total — o atalho ADICIONA, não substitui.
_KB_SHORTCUT = "knowledge_base"

# Segundo atalho, pelo mesmo motivo: `toolbox: <nome>` vira o `mcp` tool com a URL do toolbox.
# O toolbox É um servidor MCP (confirmado na documentação), então "usar este toolbox" é apontar
# para a URL dele. Montá-la à mão exige saber o endpoint do project e o formato da querystring —
# conhecimento de quem opera a plataforma, não de quem usa o produto.
_TOOLBOX_SHORTCUT = "toolbox"


class InvalidDefinition(ValueError):
    """Documento que não vira agente, com o motivo."""


def _client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    from app.modules.tenancy.public import tenant_config

    return AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def parse_definition(doc: dict) -> dict:
    """Valida um documento AgentSchema e devolve os campos de `PromptAgentDefinition`.

    Devolve dict, não o objeto do SDK, para que a validação seja testável offline sem importar
    `azure.ai.projects` — o gate roda em todo push, inclusive onde não há credencial.
    """
    if not isinstance(doc, dict):
        raise InvalidDefinition("O documento precisa ser um objeto (mapa de chaves).")

    kind = str(doc.get("kind") or doc.get("type") or "prompt").lower()
    if kind not in ("prompt", "promptagent"):
        raise InvalidDefinition(
            f"Tipo '{kind}' não é suportado ainda. Hoje criamos agentes do tipo 'prompt'."
        )

    model = doc.get("model")
    # AgentSchema aceita `model` como objeto ({id: ...}) ou string; os dois aparecem nos
    # documentos deste repo, então os dois entram.
    if isinstance(model, dict):
        model = model.get("id") or model.get("name") or model.get("deployment")
    if not model or not isinstance(model, str):
        raise InvalidDefinition("Falta `model` — o deployment do modelo que o agente usa.")

    instructions = doc.get("instructions")
    if isinstance(instructions, list):
        instructions = "\n\n".join(str(x) for x in instructions if x)
    if not instructions or not str(instructions).strip():
        raise InvalidDefinition("Falta `instructions` — o que o agente deve fazer.")

    for value in (model, str(instructions)):
        if value.strip().startswith("="):
            raise InvalidDefinition(
                "Expressão PowerFx (=...) não é avaliada aqui: sem o runtime .NET o valor "
                "chegaria literal ao serviço. Use o valor direto."
            )

    out: dict[str, Any] = {
        "kind": "prompt",
        "model": model,
        "instructions": str(instructions).strip(),
    }
    for key in _PASSTHROUGH:
        if key in doc and doc[key] is not None:
            out[key] = doc[key]

    # O atalho da base entra como uma tool a mais, preservando as que o documento já traz.
    kb = doc.get(_KB_SHORTCUT)
    if kb:
        if not isinstance(kb, str):
            raise InvalidDefinition(
                f"`{_KB_SHORTCUT}` deve ser o nome da base de conhecimento, como texto."
            )
        tools = list(out.get("tools") or [])
        tools.append(_search_tool_spec(kb))
        out["tools"] = tools

    # O atalho do toolbox entra como mais uma tool, preservando as anteriores.
    tbx = doc.get(_TOOLBOX_SHORTCUT)
    if tbx:
        if not isinstance(tbx, str):
            raise InvalidDefinition(f"`{_TOOLBOX_SHORTCUT}` deve ser o nome do toolbox, como texto.")
        tools = list(out.get("tools") or [])
        tools.append(_toolbox_tool_spec(tbx))
        out["tools"] = tools

    known = {
        "kind",
        "type",
        "model",
        "instructions",
        "name",
        "description",
        "metadata",
        _KB_SHORTCUT,
        _TOOLBOX_SHORTCUT,
        *_PASSTHROUGH,
    }
    ignored = sorted(set(doc) - known)
    return {"definition": out, "ignored": ignored}


def _toolbox_tool_spec(name: str) -> dict:
    """A forma do `mcp` tool que aponta para um toolbox.

    Usa o endpoint CONSUMER (sem versão no caminho), que serve sempre a `default_version`. É a
    escolha certa para agente: promover uma versão do toolbox — ou da skill dentro dele — passa a
    valer sem tocar no agente. Fixar a versão aqui transformaria cada promoção numa edição de
    agente.

    Import tardio para `parse_definition` continuar testável offline sem tocar em configuração.
    """
    from app.modules.foundry.internal.names import qualify as _q
    from app.modules.foundry.internal.toolboxes import mcp_url

    # A connection segue a convenção de nome de `ensure_toolbox_connection`: `<toolbox>-mcp`.
    # Referenciá-la aqui é o que evita o 401 na primeira chamada do agente.
    return mcp_url(name, connection=f"{_q(name)}-mcp")["tool"]


def _search_tool_spec(kb_name: str) -> dict:
    """A forma de `AzureAISearchTool` para uma base, como dicionário.

    Dicionário e não o objeto do SDK para que `parse_definition` permaneça testável offline — o
    gate roda em todo push, inclusive onde não há `azure.ai.projects` autenticável. A conversão
    para os tipos acontece em `create_agent_version`.

    `index_name` recebe o nome da base porque, no caminho que este produto cria, base e índice
    têm o mesmo nome: `create_knowledge` nomeia a knowledge base com o nome que o usuário deu.
    """
    return {
        "type": "azure_ai_search",
        "name": f"buscar_{kb_name}".replace("-", "_"),
        "description": f"Busca na base de conhecimento {kb_name} e devolve trechos com a fonte.",
        "azure_ai_search": {"indexes": [{"index_name": kb_name, "type": "azure_ai_search_index"}]},
    }


def create_agent_version(name: str, doc: dict, *, description: str = "") -> dict:
    """Publica uma versão do agente a partir do documento.

    Não existe "criar agente" separado de "criar versão": o recurso é versionado, e a primeira
    versão É a criação. A interface reflete isso — salvar publica versão, sempre.
    """
    from azure.ai.projects.models import PromptAgentDefinition

    parsed = parse_definition(doc)
    qualified = qualify(name)
    fields = dict(parsed["definition"])
    fields.pop("kind", None)  # o tipo é o próprio objeto

    client = _client()
    try:
        version = client.agents.create_version(
            qualified,
            definition=PromptAgentDefinition(**fields),
            metadata={"description": description[:512]} if description else None,
        )
        return {
            "name": qualified,
            "version": getattr(version, "version", None),
            "status": str(getattr(version, "status", "") or "") or None,
            # O que foi ignorado sobe na resposta: o usuário precisa saber que aquele campo do
            # documento dele não chegou ao serviço.
            "ignored_fields": parsed["ignored"],
        }
    finally:
        with contextlib.suppress(Exception):
            client.close()


def set_agent_enabled(name: str, enabled: bool) -> dict:
    """Habilita ou desabilita. Desabilitar não apaga — é o botão reversível."""
    qualified = qualify(name)
    client = _client()
    try:
        if enabled:
            client.agents.enable(qualified)
        else:
            client.agents.disable(qualified)
        return {"name": qualified, "enabled": enabled}
    finally:
        with contextlib.suppress(Exception):
            client.close()


def delete_agent(name: str) -> dict:
    """Apaga o agente e todas as suas versões.

    `force` NÃO é passado: o default do serviço recusa apagar quando há dependência, e essa
    recusa é informação — significa que algo aponta para este agente. Forçar aqui esconderia
    isso, e a mensagem do serviço é o que diz o que quebraria.
    """
    qualified = qualify(name)
    client = _client()
    try:
        client.agents.delete(qualified)
        return {"name": qualified, "deleted": True}
    finally:
        with contextlib.suppress(Exception):
            client.close()
