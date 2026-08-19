"""O helpdesk emite as fontes por API PÚBLICA — o painel de evidências não depende de monkeypatch.

POR QUE ISTO É GATE. O painel de evidências é a peça que mostra de onde cada afirmação veio, e o
helpdesk não o alimentava: ele passa pelo adapter oficial, e o adapter DESCARTA `content.annotations`
(medido — `_emit_text` lê só `content.text`, enquanto `_emit_usage`, quatro linhas abaixo, emite
`CustomEvent`). O painel caía no heurístico de texto, que adivinha nome de arquivo por regex.

A SAÍDA ESTÁ NO PRÓPRIO ADAPTER, e é ela que este teste protege. O runtime de WORKFLOW tem um ramo
genérico — rotulado por ele mesmo "custom workflow events" — que emite
`CustomEvent(name=event.type, value=event.data)` para qualquer evento fora dos tipos conhecidos. E
`WorkflowEventType` é um `Literal`: dica de tipo, sem efeito em runtime. Então
`ctx.add_event(WorkflowEvent("sources", data=...))` atravessa por API pública.

A ALTERNATIVA ERA MONKEYPATCH de `_emit_text`, função privada de módulo num pacote que a ADR-020 já
descreve como volátil. O nosso código quebra quando NÓS mexemos; um monkeypatch quebra quando ELES
publicam um minor. Este teste existe para que a rota pública não seja perdida por engano e alguém
recorra à privada.

O QUE ELE VIGIA, e por que cada item pode quebrar em silêncio:
  · o ramo genérico ainda existe no adapter — se sumir, o evento vira nada e o painel esvazia;
  · `WorkflowEventType` continua permissivo em runtime — se virar enum de verdade, a construção
    do evento passa a levantar;
  · o executor repassa a mensagem intacta — ele é observador no meio da cadeia, e um passo que
    engole a mensagem quebraria o workflow inteiro sem dizer por quê;
  · a carga é a canônica (`agent_framework.Annotation`), a mesma do caminho grounded — duas
    montagens da mesma coisa divergem no primeiro campo novo.
"""

from __future__ import annotations

import asyncio
import sys
from typing import Any

CANONICOS = ("type", "title", "url", "snippet", "index")


class _ProviderFalso:
    def citations(self) -> list[dict[str, Any]]:
        return [
            {
                "type": "citation",
                "title": "runbook-a.md",
                "url": "https://x/a",
                "snippet": "trecho",
                "index": 1,
            }
        ]


class _CtxFalso:
    def __init__(self) -> None:
        self.eventos: list[Any] = []
        self.mensagens: list[Any] = []

    def add_event(self, evento: Any) -> None:
        self.eventos.append(evento)

    async def send_message(self, mensagem: Any) -> None:
        self.mensagens.append(mensagem)


def main() -> int:
    from agent_framework import WorkflowContext, WorkflowEvent
    from agent_framework_ag_ui._workflow_run import _custom_event_value, _event_name

    from app.modules.grounded.public import SourcesExecutor

    falhas: list[str] = []

    def check(nome: str, cond: bool) -> None:
        print(f"  {'✓' if cond else '✗'} {nome}")
        if not cond:
            falhas.append(nome)

    # --- a API que a rota usa continua pública e permissiva -------------------------------
    check("`ctx.add_event` continua na superfície pública do WorkflowContext",
          hasattr(WorkflowContext, "add_event"))
    try:
        WorkflowEvent("sources", data=[])
        aceita = True
    except Exception:  # noqa: BLE001 — o ponto do check é justamente se levanta
        aceita = False
    check("`WorkflowEvent` aceita um tipo fora do Literal (é dica, não enum)", aceita)

    # --- o executor emite e repassa ---------------------------------------------------------
    ctx = _CtxFalso()
    asyncio.run(SourcesExecutor(_ProviderFalso()).on_retrieved("msg-do-retrieve", ctx))
    check("o executor emitiu exatamente um evento", len(ctx.eventos) == 1)
    check("…e repassou a mensagem INTACTA", ctx.mensagens == ["msg-do-retrieve"])

    if ctx.eventos:
        evento = ctx.eventos[0]
        # --- o adapter converteria no evento que o painel escuta ---------------------------
        check("o adapter converte em CustomEvent(name='sources')", _event_name(evento) == "sources")
        valor = _custom_event_value(evento)
        check("…com a lista de citações como valor", isinstance(valor, list) and len(valor) == 1)
        if isinstance(valor, list) and valor:
            faltando = [c for c in CANONICOS if c not in valor[0]]
            check(
                "…na forma canônica do framework" + (f" — falta {faltando}" if faltando else ""),
                not faltando,
            )

    # --- sem provider não há passo, e sem citações não há evento ---------------------------
    vazio = _CtxFalso()
    class _SemCitacoes:
        def citations(self): return []
    asyncio.run(SourcesExecutor(_SemCitacoes()).on_retrieved("msg", vazio))
    check("sem citações, nenhum evento é emitido (e a mensagem segue)",
          not vazio.eventos and vazio.mensagens == ["msg"])

    if falhas:
        print(
            f"\n❌ {len(falhas)} verificação(ões) falharam. Se o ramo genérico do adapter sumiu, a"
            "\n   rota pública morreu — NÃO troque por monkeypatch de `_emit_text`: veja ADR-025."
        )
        return 1
    print("\n✅ o helpdesk emite as fontes por API pública, na forma canônica.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
