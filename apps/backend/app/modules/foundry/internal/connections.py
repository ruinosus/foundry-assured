"""Connection de project — criada via ARM, porque o data plane não cria.

POR QUE ISTO EXISTE. Um agente que usa toolbox conecta em `/toolboxes/{nome}/mcp`, e esse
endpoint **exige credencial**: sem ela o agente recebe `401 PermissionDenied` na primeira
chamada — verificado empiricamente, não deduzido. A credencial vem de uma *project connection*
referenciada por `project_connection_id` no `mcp` tool.

POR QUE ARM E NÃO O SDK. `ConnectionsOperations` do `azure-ai-projects` tem `get`, `get_default`
e `list` — **não tem create**. Criar connection é management plane, como criar project. O caminho
oficial é `PUT .../projects/{project}/connections/{nome}` ou
`az cognitiveservices account project connection create`.

POR QUE REST DIRETO E NÃO `azure-mgmt-cognitiveservices`. A chamada é um PUT com corpo de quatro
campos. Trazer um SDK de management inteiro para isso ampliaria a superfície de dependências do
backend por causa de uma requisição — e a MÁXIMA MAIOR pede a cola mínima, não a maior. O token é
o mesmo `DefaultAzureCredential`, só com escopo de management.

O QUE ISTO EXIGE DE PERMISSÃO, e o que acontece quando falta: escrever connection é operação ARM
(`Microsoft.CognitiveServices/accounts/projects/connections/write`). A identidade da aplicação
precisa dela. Quando falta, o erro diz exatamente isso em vez de repassar um 403 cru — porque a
correção é uma atribuição de papel, e quem lê o erro precisa saber disso.
"""

from __future__ import annotations

import os
import re

_ARM = "https://management.azure.com"
_API_VERSION = "2025-06-01"

# O resource ID do storage carrega subscription e resource group, e é o único lugar do ambiente
# atual onde eles aparecem juntos. Preferimos uma variável explícita quando ela existir.
_RESOURCE_ID_RE = re.compile(r"/subscriptions/([^/]+)/resourceGroups/([^/]+)/", re.IGNORECASE)


class ConnectionError_(RuntimeError):
    """Falha ao criar/ler connection, já legível."""


def _coordinates() -> tuple[str, str, str, str]:
    """subscription, resource group, conta Foundry e project — do ambiente.

    `FOUNDRY_ACCOUNT_RESOURCE_ID` é o caminho explícito e preferido. Sem ela, deriva subscription
    e resource group do resource ID do storage, que o `azd` já preenche — mas isso assume que os
    dois recursos vivem no mesmo grupo. A suposição é razoável (o bicep provisiona junto) e está
    dita aqui em vez de escondida; quando ela não valer, a variável explícita resolve.
    """
    from app.modules.tenancy.public import tenant_config

    endpoint = (tenant_config().foundry_project_endpoint or "").rstrip("/")
    if not endpoint:
        raise ConnectionError_("FOUNDRY_PROJECT_ENDPOINT não está configurado.")

    account = endpoint.split("//")[-1].split(".")[0]
    project = endpoint.rsplit("/", 1)[-1]

    explicit = os.environ.get("FOUNDRY_ACCOUNT_RESOURCE_ID", "")
    fonte = explicit or (tenant_config().azure_storage_resource_id or "")
    match = _RESOURCE_ID_RE.match(fonte)
    if not match:
        raise ConnectionError_(
            "Não foi possível descobrir a subscription e o resource group. Defina "
            "FOUNDRY_ACCOUNT_RESOURCE_ID com o resource ID da conta do Foundry."
        )
    return match.group(1), match.group(2), account, project


def _token() -> str:
    """Token para o management plane — escopo diferente do data plane."""
    from azure.identity import DefaultAzureCredential

    return DefaultAzureCredential().get_token(f"{_ARM}/.default").token


def _url(name: str) -> str:
    sub, rg, account, project = _coordinates()
    return (
        f"{_ARM}/subscriptions/{sub}/resourceGroups/{rg}"
        f"/providers/Microsoft.CognitiveServices/accounts/{account}/projects/{project}"
        f"/connections/{name}?api-version={_API_VERSION}"
    )


def ensure_toolbox_connection(toolbox_name: str, target_url: str) -> dict:
    """Garante a connection que autentica o agente no endpoint MCP do toolbox.

    Idempotente: o PUT do ARM cria ou atualiza, então chamar de novo com o mesmo alvo não falha —
    o que importa porque isto roda toda vez que o toolbox é publicado.

    `authType: "AAD"` faz a chamada usar Entra em vez de chave: o endpoint do toolbox é do próprio
    Foundry, então autenticar com credencial da plataforma é o caminho certo — e mantém a RULE #2
    (nenhuma chave no caminho).
    """
    import httpx

    name = f"{toolbox_name}-mcp"
    body = {
        "properties": {
            # RemoteTool é a categoria que o Foundry resolve para um `mcp` tool. Criei antes como
            # CustomKeys e o agente respondeu "Connection resolution failed" — encontrava a
            # connection e não sabia o que fazer com ela. A categoria É o contrato.
            "category": "RemoteTool",
            "target": target_url,
            "authType": "AAD",
            "isSharedToAll": False,
            "metadata": {
                # Marca de origem: uma connection criada por nós é distinguível das que o operador
                # criou à mão, o que importa na hora de saber o que pode ser removido.
                "createdBy": "foundry-assured",
                "toolbox": toolbox_name,
            },
        }
    }

    try:
        r = httpx.put(
            _url(name),
            headers={"Authorization": f"Bearer {_token()}", "Content-Type": "application/json"},
            json=body,
            timeout=40.0,
        )
    except Exception as exc:
        raise ConnectionError_(f"Não foi possível falar com o Azure: {type(exc).__name__}") from exc

    if r.status_code in (401, 403):
        # A correção é uma atribuição de papel, não uma mudança de código — dizer isso poupa a
        # investigação que o 403 cru provocaria.
        raise ConnectionError_(
            "Sem permissão para criar a connection do toolbox. A identidade da aplicação precisa "
            "de escrita em Microsoft.CognitiveServices/accounts/projects/connections "
            "(papel Azure AI Project Manager ou Contributor na conta do Foundry)."
        )
    if r.status_code >= 400:
        raise ConnectionError_(f"Azure respondeu {r.status_code} ao criar a connection.")

    return {"name": name, "target": target_url, "status": r.status_code}


def delete_connection(name: str) -> dict:
    """Remove uma connection. Usada quando o toolbox some — a connection sozinha não serve."""
    import httpx

    try:
        r = httpx.delete(_url(name), headers={"Authorization": f"Bearer {_token()}"}, timeout=40.0)
    except Exception as exc:
        raise ConnectionError_(f"Não foi possível falar com o Azure: {type(exc).__name__}") from exc
    return {"name": name, "deleted": r.status_code < 400, "status": r.status_code}
