"""A projeção de agente não pode vazar vocabulário de plataforma nem esconder versão.

O módulo `foundry` é fino de propósito (MÁXIMA MAIOR: a gestão está no SDK). O pouco que ele
faz é justamente onde dá para errar:

  * repassar `AgentDetails` cru levaria `blueprint`, `instance_identity` e `agent_card` para a
    interface — campos que só significam algo para quem opera o Foundry;
  * achatar o agente sem a versão faria a interface mentir sobre o recurso, que é VERSIONADO:
    salvar publica versão, e uma tela que não mostra isso promete edição in-place.

Offline: nada de rede, nada de credencial — objetos falsos com a forma que o SDK devolve.

    uv run python -m tests.foundry.agent_projection_test
"""

from __future__ import annotations

import sys
from datetime import UTC, datetime

from app.modules.foundry.internal.agents import _latest_version, _project


class _Version:
    def __init__(self, v, status="published"):
        self.version = v
        self.description = f"versão {v}"
        self.created_at = datetime(2026, 8, 17, 12, 0, tzinfo=UTC)
        self.status = status


class _Agent:
    """A forma que `AgentDetails` tem — campos lidos do `_attribute_map` do SDK instalado."""

    def __init__(self, versions):
        self.object = "prompt"
        self.id = "agt_123"
        self.name = "meu-agente"
        self.state = "enabled"
        self.versions = versions
        self.agent_endpoint = "https://x/agents/meu-agente"
        self.instance_identity = "não deve vazar"
        self.blueprint = "não deve vazar"
        self.agent_card = {"não": "deve vazar"}


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    p = _project(_Agent([_Version("1"), _Version("2")]))

    check("nome, id e estado chegam à interface", p["name"] == "meu-agente" and p["state"] == "enabled")
    check("o endpoint do agente é preservado", p["endpoint"].endswith("/meu-agente"))

    # O ponto: o recurso é versionado, e a projeção mostra o TOPO, não a primeira.
    check("a versão corrente é a última, não a primeira", p["version"]["version"] == "2")
    check("a contagem de versões aparece (o histórico existe)", p["version_count"] == 2)
    check("a data vira string ISO (o objeto datetime não atravessa JSON)",
          isinstance(p["version"]["created_at"], str) and "2026-08-17" in p["version"]["created_at"])

    # Vocabulário de plataforma fica fora.
    vazados = {"blueprint", "instance_identity", "agent_card", "blueprint_reference"} & set(p)
    check("campos de plataforma NÃO vazam para a interface", not vazados)

    # Um agente recém-criado ainda não tem versão: não pode explodir.
    vazio = _project(_Agent([]))
    check("agente sem versão nenhuma projeta sem quebrar",
          vazio["version"] is None and vazio["version_count"] == 0)
    check("_latest_version devolve None em lista vazia", _latest_version(_Agent([])) is None)

    if falhas:
        print(f"\n❌ {len(falhas)} asserção(ões) falharam.")
        return 1
    print("\n✅ a projeção mostra a versão e não vaza vocabulário de plataforma.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
