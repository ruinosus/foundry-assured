"""Ingest dos agentes do repositório para o Foundry.

    uv run python -m cli.provision_agents          # publica todos
    uv run python -m cli.provision_agents --dry    # mostra o que faria

O PRINCÍPIO, dito pelo dono do projeto e que este arquivo existe para cumprir:

    **Tudo fica no Foundry. A diferença é QUEM colocou por lá e COMO.**

Não há "agente de código" e "agente do Foundry" — há UM lugar, e dois caminhos até ele:

    dev      →  documento AgentSchema no repo  →  ESTE ingest        →  Foundry
    usuário  →  wizard na tela                 →  POST /agents/…     →  Foundry

Depois de publicado, ninguém precisa saber por qual caminho veio. É a mesma lista, com versão,
histórico e portal — e é por isso que a tela "Meus agentes" mostrava zero enquanto o produto
exibia seis assistentes: eles nunca tinham sido publicados.

NADA É DECLARADO AQUI, e essa é a correção mais importante. A primeira versão deste arquivo
tinha uma lista `AGENTS = [...]` com nome, prompt e runtime de cada um — uma SEGUNDA VERDADE ao
lado do registry e dos documentos, que divergiria no primeiro agente novo. Agora tudo é derivado:

  * QUAIS agentes    → os documentos em `agents/helpdesk/*.yaml` (a fonte de prompt, ADR-013)
  * QUAL prompt      → `agentdefs` compõe (persona + instruções + guardrails + skills)
  * QUAL runtime     → o `kind` do domínio no `app/registry.py`

Acrescentar um agente é acrescentar um documento. Nada aqui muda.

SOBRE `metadata.runtime`. Um documento cujo domínio é `workflow` ou `graph` publica identidade,
prompt e versão — mas a execução continua no nosso backend, porque um workflow de três passos e
um grafo LangGraph com HITL não cabem num `PromptAgentDefinition`. Publicar e ficar calado
produziria um recurso que parece executável e não é. A tela lê este campo e diz onde roda.
"""

from __future__ import annotations

import sys

from app.modules.foundry.public import create_agent_version
from app.modules.tenancy.public import tenant_config

#: documento AgentSchema → domínio do registry, quando o nome não coincide.
#:
#: `helpdesk` é um workflow de três passos: `triage`, `retrieve` e `resolve` são documentos do
#: MESMO domínio. Os demais coincidem, e por isso o mapa é pequeno — ele registra a exceção, não
#: a regra.
_DOMAIN_FOR_DOC = {
    "triage": "helpdesk",
    "retrieve": "helpdesk",
    "resolve": "helpdesk",
    "concierge-grounded": "helpdesk",
    "concierge-ungrounded": "helpdesk",
}


def _runtime_for(doc_name: str) -> str:
    """Onde este agente REALMENTE executa, segundo o registry.

    `grounded` e `tool` chamam o modelo do Foundry com o prompt — o agente publicado é o agente.
    `workflow` e `graph` orquestram no nosso backend, e o recurso publicado é identidade e
    histórico. Um documento sem domínio correspondente (ex.: `techdocs`, hoje desligado) fica
    como `foundry`: é um prompt simples, e é o que ele será quando voltar.
    """
    from app.registry import DOMAIN_KINDS

    dominio = _DOMAIN_FOR_DOC.get(doc_name, doc_name)
    kind = DOMAIN_KINDS.get(dominio, "grounded")
    return "backend" if kind in ("workflow", "graph") else "foundry"


def main() -> int:
    seco = "--dry" in sys.argv

    cfg = tenant_config()
    if not cfg.foundry_project_endpoint:
        print("❌ FOUNDRY_PROJECT_ENDPOINT ausente — nada a publicar.")
        return 1

    # Importado aqui, não no topo: `agentdefs` compõe no import e falha alto se um documento
    # estiver quebrado. Deixar isso acontecer DEPOIS da checagem de configuração dá a mensagem
    # certa para o problema certo.
    from app.modules.agentdefs.public import composed_agents

    agentes = composed_agents()
    modelo = cfg.foundry_model or "gpt-5-mini"
    print(f"Ingest de {len(agentes)} agentes do repositório → Foundry (modelo {modelo}).\n")

    falhas = 0
    for nome, (instrucoes, descricao) in sorted(agentes.items()):
        runtime = _runtime_for(nome)
        rotulo = f"{nome:22} runtime={runtime}"
        if seco:
            print(f"  · {rotulo}  ({len(instrucoes)} chars)")
            continue
        try:
            out = create_agent_version(
                nome,
                {
                    "kind": "prompt",
                    "model": modelo,
                    "instructions": instrucoes,
                    "metadata": {"runtime": runtime, "source": "repo"},
                },
                description=descricao,
            )
            print(f"  ✅ {rotulo}  v{out.get('version')}")
        except Exception as exc:  # noqa: BLE001 — um agente falho não impede os outros
            falhas += 1
            print(f"  ❌ {rotulo}  {type(exc).__name__}: {str(exc)[:150]}")

    if seco:
        print("\n(simulação — nada foi publicado)")
        return 0
    if falhas:
        print(f"\n⚠ {falhas} de {len(agentes)} falharam.")
        return 1
    print(f"\n✅ {len(agentes)} agentes no Foundry. A tela 'Meus agentes' lista todos.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
