"""A decisão do HITL do LangGraph, registrada na trilha (ADR-023).

POR QUE UMA SUBCLASSE, e não um middleware nosso ao lado. A ADR-020 decidiu usar cada framework do
jeito mais canônico possível: o `HumanInTheLoopMiddleware` é a máquina de aprovação do LangGraph, e
duas máquinas decidindo poderiam discordar sobre o que foi aprovado. Aqui só se OBSERVA.

`_process_decision` é o ponto onde a decisão humana já chegou e ainda não virou ação: ela recebe o
tipo (`approve` | `edit` | `reject`), a chamada de ferramenta e a configuração. Registrar antes de
delegar garante que o evento existe mesmo que o processamento seguinte falhe.

O QUE ENTRA: o tipo da decisão, o nome da ferramenta e — no `edit` — QUE CAMPOS foram corrigidos.
Os VALORES não entram: argumento de ferramenta carrega o conteúdo da operação, e a trilha é
imutável.

NÃO É FAIL-CLOSED, e a assimetria com `hitl.decide` é deliberada: ali a nossa função decide E
executa, então bloquear é possível; aqui quem executa é o grafo, e levantar no meio do
processamento deixaria a máquina de estado num ponto que não controlamos. O evento de ESCRITA
cobre o resultado — `create_ticket` registra toda abertura de chamado, por qualquer caminho.
"""

from __future__ import annotations

import contextlib

from langchain.agents.middleware.human_in_the_loop import HumanInTheLoopMiddleware


class RecordingHumanInTheLoop(HumanInTheLoopMiddleware):
    """O HITL do LangGraph, com a decisão registrada. Comportamento idêntico ao original."""

    #: O domínio que usa esta instância — entra no evento para separar `oncall` de `deepcall`, que
    #: rodam o MESMO prompt em harnesses diferentes. Sem isso, a comparação entre os dois, que é a
    #: razão de o gêmeo existir, não teria como ser feita pela trilha.
    domain: str = "graph"

    @staticmethod
    def _registrar(dominio: str, decision, tool_call) -> None:
        with contextlib.suppress(Exception):
            from app.modules.audit.public import actor, actor_detail, record

            tipo = str((decision or {}).get("type") or "?")
            ferramenta = str((tool_call or {}).get("name") or "?")
            detalhe = {"decision": tipo, "domain": dominio, **actor_detail()}
            if tipo == "edit":
                editada = ((decision or {}).get("edited_action") or {}).get("args") or {}
                detalhe["edited_fields"] = sorted(editada)

            record(
                scope="approvals",
                actor=actor(),
                kind="approval",
                summary=f"{tipo} em {ferramenta}",
                ref=ferramenta,
                detail=detalhe,
            )

    def _process_decision(self, decision, tool_call, config):  # type: ignore[override]
        # No original é `@staticmethod`, mas o chamador usa `self._process_decision(...)` — o que
        # faz um override de INSTÂNCIA funcionar sem tocar em quem chama. Sobrescrever como método
        # normal é o que permite ler `self.domain`.
        self._registrar(self.domain, decision, tool_call)
        return HumanInTheLoopMiddleware._process_decision(decision, tool_call, config)


def recording_hitl(interrupt_on: dict, domain: str) -> RecordingHumanInTheLoop:
    """O middleware pronto, com o domínio que aparece no evento."""
    mw = RecordingHumanInTheLoop(interrupt_on=interrupt_on)
    mw.domain = domain
    return mw
