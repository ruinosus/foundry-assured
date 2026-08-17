"""HTTP para os recursos do Foundry que o usuário final cria e mantém.

Leitura exige apenas autenticação: ver o catálogo é o passo que traz o usuário para dentro.
Escrita exige **Admin** — criar agente, apagar base e importar repositório mudam o que as outras
pessoas veem, e no modo `shared` mudam o que outro tenant paga.

`require_role("Admin")` entra por rota, não só no router: a autorização é re-checada no servidor
mesmo com a interface escondendo o botão. A interface não é fronteira de segurança.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile

from app.modules.foundry.public import (
    create_agent_version,
    create_knowledge,
    create_skill,
    create_skill_from_files,
    create_toolbox_version,
    delete_agent,
    delete_knowledge,
    delete_skill,
    delete_toolbox,
    get_agent,
    get_knowledge,
    get_skill,
    get_toolbox,
    ingest_repo,
    list_agents,
    list_knowledge,
    list_skills,
    list_toolboxes,
    mcp_url,
    set_agent_enabled,
    upload_files,
)
from app.shared.auth import auth_dependencies, require_role

router = APIRouter(prefix="/foundry", tags=["foundry"], dependencies=auth_dependencies())

# Escrita é privilégio de Admin. Uma dependência só, reusada, para não existir rota de escrita
# que esqueceu de checar.
_admin = [Depends(require_role("Admin"))]


def _guard(fn):
    """Falha do SDK/serviço vira HTTP legível.

    Sem isto, um projeto sem agentes ou uma credencial sem permissão chega ao browser como 500
    mudo — o mesmo defeito que /admin/users tinha e que custou uma hora para diagnosticar.

    Erro de VALIDAÇÃO nossa (nome fora do formato, documento sem `model`, arquivo recusado) é
    400, não 502: a causa está no pedido, e devolver 502 mandaria a pessoa procurar problema no
    Azure quando o problema é o campo que ela preencheu.
    """
    from app.modules.foundry.internal.agent_write import InvalidDefinition
    from app.modules.foundry.internal.github_source import GitHubError
    from app.modules.foundry.internal.knowledge_write import UploadRejected
    from app.modules.foundry.internal.names import InvalidName
    from app.modules.foundry.internal.skills import InvalidSkill
    from app.modules.foundry.internal.toolboxes import InvalidToolbox

    try:
        return fn()
    except HTTPException:
        raise
    except (InvalidName, InvalidDefinition, InvalidSkill, InvalidToolbox, UploadRejected) as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except GitHubError as exc:
        # 502: a falha é do serviço de terceiro, não do pedido — e a mensagem já é legível.
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Foundry: {exc}") from exc


# ── Agentes ───────────────────────────────────────────────────────────────────────────────


@router.get("/project")
def project() -> dict:
    """Qual project do Foundry este ambiente está usando.

    Existe porque todos os recursos — agentes, bases, skills, toolboxes, connections — vivem
    DENTRO de um project, e a interface não dizia qual. Sem isso, alguém olhando uma lista vazia
    não sabe se não há nada ou se está olhando o lugar errado.

    Devolve o NOME e o host, nunca o endpoint completo com credencial de caminho: o endpoint é
    configuração de infraestrutura, e a tela só precisa do rótulo.
    """
    from urllib.parse import urlparse

    from app.modules.tenancy.public import tenant_config

    raw = (tenant_config().foundry_project_endpoint or "").rstrip("/")
    parsed = urlparse(raw)
    # `.../api/projects/<nome>` — o nome é o último segmento.
    name = raw.rsplit("/", 1)[-1] if "/projects/" in raw else ""
    return {"name": name or None, "host": parsed.netloc or None}


@router.get("/agents")
def agents(limit: int = Query(50, ge=1, le=100)) -> dict:
    return {"agents": _guard(lambda: list_agents(limit))}


@router.get("/agents/{name}")
def agent(name: str) -> dict:
    """Um agente com o histórico de versões e as sessões recentes."""
    return _guard(lambda: get_agent(name))


@router.post("/agents/{name}/versions", dependencies=_admin)
def publish_version(name: str, body: dict) -> dict:
    """Publica uma versão a partir de um documento AgentSchema.

    Não há "criar" separado de "versionar": o recurso é versionado, e a primeira versão É a
    criação. Uma rota só para os dois casos evita que a interface prometa edição in-place.
    """
    doc = body.get("definition") if isinstance(body.get("definition"), dict) else body
    return _guard(
        lambda: create_agent_version(name, doc, description=str(body.get("description") or ""))
    )


@router.post("/agents/{name}/enable", dependencies=_admin)
def enable_agent(name: str) -> dict:
    return _guard(lambda: set_agent_enabled(name, True))


@router.post("/agents/{name}/disable", dependencies=_admin)
def disable_agent(name: str) -> dict:
    """Desabilitar é o botão reversível — não apaga versão nem sessão."""
    return _guard(lambda: set_agent_enabled(name, False))


@router.delete("/agents/{name}", dependencies=_admin)
def remove_agent(name: str) -> dict:
    return _guard(lambda: delete_agent(name))


# ── Conhecimento ──────────────────────────────────────────────────────────────────────────


@router.get("/knowledge")
def knowledge(limit: int = Query(50, ge=1, le=100)) -> dict:
    """Bases e fontes numa só resposta — a tela mostra as duas juntas."""
    return _guard(lambda: list_knowledge(limit))


@router.get("/knowledge/{name}")
def knowledge_base(name: str) -> dict:
    """Uma base com o status de sincronização de cada fonte."""
    return _guard(lambda: get_knowledge(name))


@router.post("/knowledge", dependencies=_admin)
def make_knowledge(body: dict) -> dict:
    """Cria fonte + base. Idempotente: repetir o nome atualiza em vez de falhar."""
    return _guard(
        lambda: create_knowledge(
            str(body.get("name") or ""),
            description=str(body.get("description") or ""),
            answer_instructions=str(body.get("answer_instructions") or ""),
        )
    )


@router.delete("/knowledge/{name}", dependencies=_admin)
def remove_knowledge(
    name: str,
    delete_container: bool = Query(
        False,
        description=(
            "Apagar também os arquivos originais no storage. Default False: reindexar é "
            "reversível, apagar os documentos não."
        ),
    ),
) -> dict:
    return _guard(lambda: delete_knowledge(name, delete_container=delete_container))


@router.post("/knowledge/{name}/files", dependencies=_admin)
async def add_files(name: str, files: list[UploadFile] = File(...)) -> dict:  # noqa: B008 — idioma do FastAPI
    """Sobe arquivos para o container da base.

    O conteúdo é lido aqui (não no módulo interno) porque `UploadFile` é assíncrono e a leitura
    precisa acontecer antes de o request fechar. Os tetos por arquivo e por lote são checados no
    módulo interno, onde ficam testáveis offline.
    """
    payload = [(f.filename or "arquivo", await f.read()) for f in files]
    return _guard(lambda: upload_files(name, payload))


@router.post("/knowledge/{name}/github", dependencies=_admin)
def add_github(name: str, body: dict) -> dict:
    """Importa os arquivos de texto de um repositório do GitHub para a base.

    O token vem no CORPO, nunca na querystring: querystring vai para log de acesso, telemetria e
    histórico do browser (NORDOR-122 — dado sensível não trafega por URL). Ele é usado nas
    chamadas e descartado; não é persistido nem devolvido.
    """
    return _guard(
        lambda: ingest_repo(
            name,
            str(body.get("repo") or ""),
            str(body.get("token") or ""),
            ref=str(body.get("ref") or ""),
            subdir=str(body.get("subdir") or ""),
        )
    )


# ── Skills ────────────────────────────────────────────────────────────────────────────────
#
# Skill é recurso versionado como o agente, e com uma diferença que a tela precisa mostrar:
# `default_version` e `latest_version` são campos SEPARADOS. Publicar não troca o que está em uso
# se `default` não acompanhar — e é a explicação de "publiquei e nada mudou".


@router.get("/skills")
def skills(limit: int = Query(50, ge=1, le=100)) -> dict:
    return {"skills": _guard(lambda: list_skills(limit))}


@router.get("/skills/{name}")
def skill(name: str) -> dict:
    return _guard(lambda: get_skill(name))


@router.post("/skills/{name}", dependencies=_admin)
def publish_skill(name: str, body: dict) -> dict:
    """Cria ou versiona uma skill a partir de um documento no formato agentskills.io."""
    doc = body.get("content") if isinstance(body.get("content"), dict) else body
    return _guard(lambda: create_skill(name, doc, make_default=bool(body.get("default", True))))


@router.delete("/skills/{name}", dependencies=_admin)
def remove_skill(name: str) -> dict:
    return _guard(lambda: delete_skill(name))


@router.post("/skills/{name}/files", dependencies=_admin)
async def publish_skill_files(
    name: str,
    files: list[UploadFile] = File(...),  # noqa: B008 — idioma do FastAPI
) -> dict:
    """Publica uma versão de skill a partir de um BUNDLE — um zip, ou vários arquivos.

    É o caminho que a versão inline não cobre: skill de verdade tem scripts, templates e
    referências, não só uma string de instruções. O serviço extrai e valida o zip do lado dele.
    """
    payload = [(f.filename or "arquivo", await f.read()) for f in files]
    return _guard(lambda: create_skill_from_files(name, payload))


# ── Toolboxes ─────────────────────────────────────────────────────────────────────────────
#
# É o que junta tools e skills num pacote. Skill NÃO entra em `PromptAgentDefinition.tools` —
# uma skill só chega a um agente passando por aqui. Tools (MCP, Azure AI Search…) entram nos dois
# lugares; skill, só no toolbox.


@router.get("/toolboxes")
def toolboxes(limit: int = Query(50, ge=1, le=100)) -> dict:
    return {"toolboxes": _guard(lambda: list_toolboxes(limit))}


@router.get("/toolboxes/{name}")
def toolbox(name: str) -> dict:
    """Um toolbox com as versões e o que cada uma entrega."""
    return _guard(lambda: get_toolbox(name))


@router.post("/toolboxes/{name}", dependencies=_admin)
def publish_toolbox(name: str, body: dict) -> dict:
    """Publica uma versão com as tools e as skills informadas.

    `skills` aceita nome solto ou {name, version}. Sem versão, o serviço usa a default da skill.
    """
    return _guard(lambda: create_toolbox_version(name, body))


@router.delete("/toolboxes/{name}", dependencies=_admin)
def remove_toolbox(name: str) -> dict:
    return _guard(lambda: delete_toolbox(name))


@router.get("/toolboxes/{name}/mcp")
def toolbox_mcp(name: str, version: str = Query("", description="Fixa uma versão; vazio usa a default")) -> dict:
    """A URL MCP do toolbox e o `mcp` tool pronto para colar num agente.

    É ISTO que liga um agente a um toolbox: não há campo dedicado, o toolbox é um servidor MCP e o
    agente aponta para a URL. Sem versão, o endpoint serve a `default_version` — promover passa a
    valer sem tocar no agente.
    """
    return _guard(lambda: mcp_url(name, version))
