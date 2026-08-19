"""Emite as fontes recuperadas como evento AG-UI — por API pública, sem tocar no adapter.

MORA EM `grounded` PORQUE É DELE O ASSUNTO: ele emite citações, e quem as produz é o
`GroundedRetrieval` deste mesmo módulo. O helpdesk o usa (a aresta `helpdesk -> grounded` já
existe), e o caminho grounded-como-agente também — uma peça, dois consumidores, mesma carga.

POR QUE ESTE EXECUTOR EXISTE, e por que ele é pequeno de propósito. O painel de evidências é
alimentado por um `CustomEvent(name="sources")`. O caminho grounded escrito à mão o emite dentro do
próprio laço de SSE. O helpdesk não emitia — ele passa pelo adapter oficial, e o adapter descarta
`content.annotations` (medido: `_emit_text` lê só `content.text`, enquanto `_emit_usage`, quatro
linhas abaixo, emite `CustomEvent`). Resultado: o painel do helpdesk caía no heurístico de texto,
que adivinha nome de arquivo por regex.

A SAÍDA NÃO É MONKEYPATCH. O runtime de WORKFLOW do adapter tem um ramo genérico — rotulado por ele
mesmo "custom workflow events" — que emite `CustomEvent(name=event.type, value=event.data)` para
qualquer evento que não case os tipos conhecidos. E `WorkflowEventType` é um `Literal`, ou seja,
dica de tipo sem efeito em runtime. Então `ctx.add_event(WorkflowEvent("sources", data=...))`
atravessa por API pública, e o frontend recebe exatamente o mesmo evento que já escuta.

A FOLGA, dita em vez de escondida: `"sources"` está FORA do `Literal`, então um verificador de tipo
reclama — é queixa de tipo, não de runtime, e o ramo genérico existe justamente para isto. Se um dia
o adapter passar a emitir `annotations` sozinho (upstream microsoft/agent-framework#7460), este
executor sai inteiro e o frontend não muda, porque a carga já é a canônica.
"""

from __future__ import annotations

from typing import Any

from agent_framework import Executor, WorkflowContext, WorkflowEvent, handler


class SourcesExecutor(Executor):
    """Repassa a mensagem adiante e emite as fontes que a recuperação trouxe.

    Fica ENTRE o retrieve e o resolve porque é ali que os documentos existem e ainda não foram
    usados — emitir depois da resposta faria o painel só aparecer no fim, e a pessoa lê a resposta
    enquanto ela chega.

    Passa a mensagem intacta: este executor é um observador no meio da cadeia, não uma etapa que
    transforma. Um passo que altera o que passa por ele viraria lugar para regra escondida.
    """

    def __init__(self, provider: Any, *, executor_id: str = "sources") -> None:
        super().__init__(id=executor_id)
        self._provider = provider

    @handler
    async def on_retrieved(self, message: Any, ctx: WorkflowContext[Any, Any]) -> None:
        citacoes = []
        try:
            citacoes = self._provider.citations()
        except Exception:  # noqa: BLE001 — sem fontes o painel cai no heurístico, e a conversa segue
            citacoes = []
        if citacoes:
            ctx.add_event(WorkflowEvent("sources", data=citacoes))
        await ctx.send_message(message)
