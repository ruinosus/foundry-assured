"""O fluxo DECLARADO roda — e o passo humano vira o mesmo gate que a tela já sabe mostrar.

POR QUE ESTE GATE EXISTE. `agents/assured/workflows/helpdesk.yaml` foi escrito na ADR-021 com um
comentário que se explica sozinho: *"existe para provar o runtime ANTES de alguém construir um
editor: um canvas que produz YAML que não roda é um editor decorativo, e descobrir isso depois do
editor pronto seria caro."*

O editor foi construído. O YAML nunca rodou. `usecases.write_flow` monta o fluxo para VALIDAR e
descarta o objeto — o canvas desenha um fluxo que ninguém executa, e "declare o passo humano e
ele vira um gate" era uma frase sem prova.

O QUE ESTE GATE PROVA, offline e sem modelo:

1. o YAML declarado do helpdesk monta um `Workflow` de verdade;
2. um passo humano declarado PAUSA, com `ev.type == "request_info"` — o mesmo evento que
   `TicketApproval.tsx` já escuta, sem adaptador entre os dois;
3. a decisão humana RETOMA o fluxo, e os passos seguintes rodam;
4. um YAML que cita um agente inexistente falha ao MONTAR, não na primeira execução.

TRÊS ARMADILHAS DE ASSINATURA, medidas contra o pacote instalado (`agent_framework_declarative`
1.0.2) — cada uma custou uma tentativa, e é por isso que a regra 1 deste repo existe:

  * há DOIS `request_id`: `ev.request_id` (o do evento, que a retomada usa) e `ev.data.request_id`
    (o do executor). Usar o segundo devolve "Response provided for unknown request ID";
  * `ev.request_id` só existe quando `ev.type == "request_info"` — lê-lo em qualquer outro evento
    levanta, então o filtro por tipo não é estilo;
  * a resposta é um `ExternalInputResponse(user_input=…)`, não uma string, e o construtor NÃO
    aceita `request_id` (o id é a chave do dicionário `responses`).

    uv run python -m tests.helpdesk.declarative_workflow_test
"""

from __future__ import annotations

import asyncio
import sys
from pathlib import Path

import app as _app

BACKEND = Path(_app.__file__).resolve().parent.parent
FLUXO_HELPDESK = BACKEND / "agents" / "assured" / "workflows" / "helpdesk.yaml"

#: Um passo humano declarado, no vocabulário que o canvas emite (`flowCanvas.ts` serializa
#: `approval` e `question` para isto). Mínimo de propósito: o que se prova aqui é a PAUSA, e um
#: agente no meio exigiria modelo e tiraria o gate do CI offline.
YAML_PASSO_HUMANO = """
kind: Workflow
trigger:
  kind: OnConversationStart
  id: prova_gate
  actions:
    - kind: Question
      id: aprovar
      text: "Abrir chamado para o time de identidade?"
      variable: Local.Decisao
    - kind: SendActivity
      id: eco
      activity: "Decisão: {{Local.Decisao}}"
    - kind: EndWorkflow
      id: fim
"""

YAML_AGENTE_INEXISTENTE = """
kind: Workflow
trigger:
  kind: OnConversationStart
  id: fantasma
  actions:
    - kind: InvokeAzureAgent
      id: passo
      agent:
        name: AgenteQueNaoExiste
    - kind: EndWorkflow
      id: fim
"""


async def _rodar() -> tuple[list[str], str | None, list[str]]:
    """Roda o fluxo com passo humano até pausar, responde, e devolve o que aconteceu."""
    from agent_framework_declarative import ExternalInputResponse, WorkflowFactory

    wf = WorkflowFactory().create_workflow_from_yaml(YAML_PASSO_HUMANO)

    pausas: list[str] = []
    rid: str | None = None
    async for ev in wf.run("oi", stream=True):
        # O filtro por TIPO não é estilo: `ev.request_id` levanta em qualquer outro evento.
        if ev.type == "request_info":
            rid = ev.request_id
            pausas.append(str(ev.data.message))

    executados: list[str] = []
    if rid:
        resposta = ExternalInputResponse(user_input="aprovado")
        async for ev in wf.run(responses={rid: resposta}, stream=True):
            if ev.type == "executor_completed":
                executados.append(str(ev.executor_id))
    return pausas, rid, executados


def main() -> int:
    falhas: list[str] = []

    def check(nome: str, cond: bool, detalhe: str = "") -> None:
        print(f"  {'✓' if cond else '✗'} {nome}{f'  ({detalhe})' if detalhe and not cond else ''}")
        if not cond:
            falhas.append(nome)

    from app.modules.helpdesk.public import build_declarative_workflow

    # --- 1 · o fluxo do helpdesk monta -------------------------------------------------
    check("o YAML do helpdesk existe", FLUXO_HELPDESK.is_file(), str(FLUXO_HELPDESK))
    if FLUXO_HELPDESK.is_file():
        wf = build_declarative_workflow(FLUXO_HELPDESK.read_text(encoding="utf-8"))
        check("…e monta um Workflow", type(wf).__name__ == "Workflow", type(wf).__name__)

    # --- 2 e 3 · o passo humano pausa e retoma -----------------------------------------
    pausas, rid, executados = asyncio.run(_rodar())
    check("o passo humano PAUSA o fluxo", len(pausas) == 1, f"{len(pausas)} pausa(s)")
    check(
        "…com a pergunta declarada no YAML",
        pausas and "Abrir chamado" in pausas[0],
        str(pausas),
    )
    check("…e um request_id para a retomada", bool(rid))
    check("a decisão humana RETOMA o fluxo", "aprovar" in executados, str(executados))
    check("…e os passos seguintes rodam", {"eco", "fim"} <= set(executados), str(executados))

    # --- 4 · agente inexistente falha ao MONTAR ----------------------------------------
    # Falhar aqui é o que faz o erro aparecer em `write_flow`, onde alguém está editando o fluxo,
    # em vez de na primeira conversa de alguém que não escreveu o YAML.
    try:
        build_declarative_workflow(YAML_AGENTE_INEXISTENTE)
        check("agente inexistente é recusado na montagem", False, "montou sem reclamar")
    except Exception as exc:  # noqa: BLE001 — qualquer recusa serve; o que importa é NÃO montar
        check(
            "agente inexistente é recusado na montagem",
            "AgenteQueNaoExiste" in str(exc) or "agent" in str(exc).lower(),
            f"{type(exc).__name__}: {str(exc)[:90]}",
        )

    if falhas:
        print(f"\n❌ {len(falhas)} verificação(ões) falharam.")
        return 1
    print("\n✅ o fluxo declarado roda, e o passo humano é o gate que a tela já mostra.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
