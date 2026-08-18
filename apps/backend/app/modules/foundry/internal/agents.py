"""Agentes do Foundry — leitura, via SDK oficial.

MÁXIMA MAIOR: a gestão de agentes já existe como recurso. `AgentsOperations` traz 23
operações (list, get, create_version, sessões, enable/disable), então este módulo não
implementa gestão — ele projeta o que o SDK devolve para a forma que a interface consome, e
nada mais.

O que a projeção resolve, e que é trabalho legítimo nosso:

  * o SDK devolve página com continuação; a interface quer uma lista;
  * `AgentDetails` traz `blueprint`, `instance_identity`, `agent_card` — campos que só fazem
    sentido para quem opera o Foundry. Um usuário final quer nome, estado, versão e quando
    mudou. Repassar o objeto cru vazaria vocabulário de plataforma para dentro do produto.

Verificado contra o SDK INSTALADO (RULE #1), não contra a documentação: os campos abaixo saem
de `AgentDetails._attribute_map` e `AgentVersionDetails._attribute_map`.
"""

from __future__ import annotations

from typing import Any

from app.modules.tenancy.public import tenant_config


def _client():
    """Cliente do projeto, autenticado pela identidade da aplicação (RULE #2 — sem chave)."""
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    return AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def _iso(value: Any) -> Any:
    """`datetime` não atravessa JSON; ISO atravessa."""
    return value.isoformat() if hasattr(value, "isoformat") else value


def _versions_map(details: Any) -> dict:
    """`versions` como mapa.

    NÃO é uma lista, embora o nome sugira: é `AgentObjectVersions`, um mapa cuja chave `latest`
    traz a versão corrente. Escrevi `versions[-1]` e passou meses sem quebrar — porque o projeto
    não tinha agente nenhum. Na primeira publicação real: `KeyError: -1`.

    A lição é sobre o gate, não sobre o índice: `agent_projection_test` planta uma LISTA de
    versões, que é a forma que eu supus, então validava a suposição em vez do serviço. Um objeto
    falso só protege se tiver a forma do real.
    """
    versions = getattr(details, "versions", None)
    if versions is None:
        return {}
    if hasattr(versions, "items"):
        return dict(versions.items())
    # Lista (a forma que o gate planta, e que alguma versão do SDK pode devolver).
    return {"latest": versions[-1]} if versions else {}


def _field(obj: Any, name: str, default=None):
    """Campo de objeto OU de dict — as versões chegam como dict dentro do mapa."""
    if isinstance(obj, dict):
        return obj.get(name, default)
    return getattr(obj, name, default)


def _latest_version(details: Any) -> dict | None:
    """A versão corrente, achatada. Agente é recurso VERSIONADO: o que a lista mostra é o topo."""
    top = _versions_map(details).get("latest")
    if top is None:
        return None
    # `runtime` diz ONDE o agente executa: `foundry` roda no serviço; `backend` significa que o
    # recurso guarda identidade, prompt e histórico, mas quem orquestra é o nosso backend (um
    # workflow de três passos não cabe num PromptAgentDefinition). Sem este campo a tela trataria
    # os dois como iguais, e prometeria execução que não acontece lá.
    metadata = _field(top, "metadata") or {}
    return {
        "version": _field(top, "version"),
        "description": _field(top, "description") or _field(metadata, "description"),
        "created_at": _iso(_field(top, "created_at")),
        "status": str(_field(top, "status", "") or "") or None,
        "runtime": _field(metadata, "runtime"),
        "source": _field(metadata, "source"),
        # O METADATA CRU, além dos campos que a lista destaca. Sem ele, quem lê a projeção não
        # alcançava `use_case` nem `surface` — e a agregação de casos de uso caía sempre no
        # fallback, sem erro nenhum. Destacar alguns campos e esconder o resto fez a projeção
        # decidir, por omissão, o que os outros módulos podem saber.
        "metadata": dict(metadata) if isinstance(metadata, dict) else {},
    }


def _project(details: Any) -> dict:
    """Um agente na forma que a interface consome — não o objeto de plataforma."""
    return {
        "name": getattr(details, "name", None),
        "id": getattr(details, "id", None),
        "state": str(getattr(details, "state", "") or "") or None,
        "kind": str(getattr(details, "object", "") or "") or None,
        "endpoint": getattr(details, "agent_endpoint", None),
        "version": _latest_version(details),
        "version_count": len(_versions_map(details)),
    }


def list_agents(limit: int = 50) -> list[dict]:
    """Os agentes do projeto, já paginados até o fim e projetados.

    `limit` é o teto do que devolvemos, não o da chamada: o SDK aceita no máximo 100 por página
    e devolve um iterador que continua sozinho. Parar cedo é decisão nossa; parar em silêncio
    seria mentira, então o chamador recebe exatamente o que pediu e o teto fica documentado.
    """
    client = _client()
    try:
        out: list[dict] = []
        for item in client.agents.list():
            out.append(_project(item))
            if len(out) >= limit:
                break
        return out
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            client.close()


def _project_version(v: Any) -> dict:
    """Uma versão do histórico. Mesma forma da versão corrente, para a tela não precisar de dois
    formatos ao mostrar "atual" e "anteriores" na mesma lista."""
    return {
        "version": _field(v, "version"),
        "description": _field(v, "description"),
        "created_at": _iso(_field(v, "created_at")),
        "status": str(_field(v, "status", "") or "") or None,
    }


def _project_session(s: Any) -> dict:
    """Uma sessão, na forma que a tela consome.

    Campos verificados em `AgentSessionResource`: agent_session_id, created_at, expires_at,
    last_accessed_at, status, version_indicator. `version_indicator` é o que amarra a sessão à
    versão que a atendeu — é a pergunta "com qual versão isso rodou?", que é o motivo de a tela
    de detalhe existir.
    """
    return {
        "id": getattr(s, "agent_session_id", None),
        "status": str(getattr(s, "status", "") or "") or None,
        "created_at": _iso(getattr(s, "created_at", None)),
        "last_accessed_at": _iso(getattr(s, "last_accessed_at", None)),
        "expires_at": _iso(getattr(s, "expires_at", None)),
        "version": str(getattr(s, "version_indicator", "") or "") or None,
    }


def get_agent(name: str, *, sessions_limit: int = 20) -> dict:
    """Um agente pelo nome, com o histórico de versões e as sessões recentes.

    A lista traz só a versão do topo; aqui vem o histórico inteiro, porque é o que responde a
    pergunta da tela de detalhe: *o que mudou, quando, e o que estava no ar quando aquela
    conversa aconteceu*. Agente é recurso versionado — esconder o histórico faria a interface
    prometer edição in-place, que não é o que o serviço faz.

    Falha ao listar sessões NÃO derruba a página: nem todo agente tem sessões, e a permissão
    para ler o agente não implica permissão para ler as sessões dele. `sessions` vira `null` e
    o resto continua legível — perder a página por causa de uma seção seria pior que mostrar a
    página com a lacuna visível.
    """
    import contextlib

    client = _client()
    try:
        details = client.agents.get(name)
        out = _project(details)
        out["versions"] = [_project_version(v) for v in _versions_map(details).values()]
        try:
            out["sessions"] = [
                _project_session(s)
                for s in client.agents.list_sessions(name, limit=sessions_limit)
            ]
        except Exception:  # noqa: BLE001 — o agente vale mais que a lista de sessões
            out["sessions"] = None
        return out
    finally:
        with contextlib.suppress(Exception):
            client.close()
