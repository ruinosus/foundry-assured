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


def _latest_version(details: Any) -> dict | None:
    """A versão corrente, achatada. Agente é recurso VERSIONADO: `versions` é o histórico, e o
    que a lista mostra é o topo dele. Esconder isso faria a interface mentir sobre o recurso."""
    versions = getattr(details, "versions", None) or []
    if not versions:
        return None
    top = versions[-1]
    return {
        "version": getattr(top, "version", None),
        "description": getattr(top, "description", None),
        "created_at": _iso(getattr(top, "created_at", None)),
        "status": str(getattr(top, "status", "") or "") or None,
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
        "version_count": len(getattr(details, "versions", None) or []),
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


def get_agent(name: str) -> dict:
    """Um agente pelo nome. Levanta o erro do SDK — a camada HTTP o traduz."""
    client = _client()
    try:
        return _project(client.agents.get(name))
    finally:
        import contextlib

        with contextlib.suppress(Exception):
            client.close()
