"""A recuperação com ACL, no seam do próprio framework.

POR QUE ISTO EXISTE. O caminho grounded (techdocs, selfwiki) é o único dos quatro runtimes que
grava tudo — e é o mais ARTESANAL: um laço de SSE escrito à mão, com `record_turn` e `record_usage`
chamados explicitamente dentro dele. Quanto mais artesanal, pior, porque nada disso se propaga: o
helpdesk recupera fontes pelo `AzureAISearchContextProvider` do framework e a contagem morre ali.

A pergunta certa não era "como espalhar o que o caminho artesanal faz", e sim **qual é exatamente a
lacuna que justifica ele existir**. Medida: `AzureAISearchContextProvider` cobre grounding e
citação, e NÃO envia `x-ms-query-source-authorization` — o header de ACL por usuário (zero
ocorrências em 998 linhas do módulo). Sem ele cai o controle de acesso por documento, que é a
RULE #6 e tem gate próprio. **É essa a lacuna, e é só ela.** O laço de SSE em volta não é lacuna,
é acúmulo.

Então o que sobrevive de nosso é o `retrieve()` com ACL — e ele entra por `ContextProvider`, que é
o ponto de extensão do framework para exatamente isto. Não é padrão novo: `StoredHistoryProvider`
já foi escrito assim, e `HistoryProvider` É um `ContextProvider` (mesmo MRO).

O QUE ISSO DESTRAVA DE UMA VEZ: plugado no `retrieve` do helpdesk no lugar do provider do
framework, ele dá ao helpdesk a contagem de referências **e** o controle de acesso por documento
que ele não tinha — os dois num movimento só. E qualquer agente futuro com base ganha os dois por
usar o provider, não por alguém lembrar.

O USUÁRIO É CAPTURADO NA CONSTRUÇÃO, não lido no `before_run`: `retrieve()` precisa da identidade
para trimar por ACL, e quem constrói o agente está no contexto da requisição. É a mesma disciplina
que o caminho grounded já documenta ("the user MUST be captured in the endpoint and passed in").
"""

from __future__ import annotations

import logging
from typing import Any

from agent_framework import ContextProvider

logger = logging.getLogger(__name__)


class GroundedRetrieval(ContextProvider):
    """Injeta documentos autorizados no contexto, e conta as referências que injetou."""

    def __init__(self, user: Any, domain: Any, *, source_id: str = "grounded_retrieval",
                 agent_id: str = "", top: int = 8) -> None:
        super().__init__(source_id)
        self._user = user
        self._domain = domain
        self._agent = agent_id or getattr(domain, "id", "") or "grounded"
        self._top = top
        #: Os documentos da ÚLTIMA busca desta requisição. Lido por quem precisa mostrá-los.
        self.ultimos_documentos: list[dict] = []

    def citations(self) -> list[dict]:
        """As citações no vocabulário do framework (`agent_framework.Annotation`).

        Mesma forma que o caminho grounded emite — `type`/`title`/`url`/`snippet` mais o `index`
        que amarra a citação `[n]` do texto ao item da lista. Uma função só para as duas rotas
        produzirem a MESMA carga: duas montagens da mesma coisa divergem no primeiro campo novo,
        e a tela não teria como saber qual das duas está certa.
        """
        return [
            {
                "type": "citation",
                "title": d["source"],
                "url": d.get("url"),
                "snippet": (d.get("snippet") or "")[:800],
                "index": d["index"],
            }
            for d in self.ultimos_documentos
        ]

    @staticmethod
    def _pergunta(context: Any) -> str:
        """O texto da última mensagem do usuário, que é o que se busca.

        `include_input=True` porque a pergunta desta rodada ainda não é histórico — sem isso a
        busca aconteceria sobre o turno ANTERIOR, o que não dá erro e responde a pergunta errada.
        """
        try:
            mensagens = context.get_messages(include_input=True)
        except Exception:  # noqa: BLE001 — sem mensagens não há o que buscar
            return ""
        for mensagem in reversed(list(mensagens)):
            if getattr(mensagem, "role", "") == "user":
                return str(getattr(mensagem, "text", "") or "")
        return ""

    async def before_run(self, *, agent, session, context, state) -> None:  # type: ignore[override]
        from app.modules.grounded.internal.grounded import SYNTHESIS_DIRECTIVE
        from app.modules.knowledge.public import retrieve

        pergunta = self._pergunta(context)
        if not pergunta:
            return
        try:
            docs = await retrieve(pergunta, self._user, self._domain, top=self._top)
        except Exception:
            # Recuperação que falha NÃO vira resposta sem fonte: o agente segue sem contexto e a
            # policy de citação (RULE #4) reprova a resposta, que é o comportamento correto —
            # melhor uma recusa do que uma resposta fundamentada em nada.
            logger.exception("recuperação falhou para o domínio %s", self._agent)
            return

        state["referencias"] = len(docs)
        # Os documentos ficam NA INSTÂNCIA, e isso é seguro porque ela é construída por requisição
        # (`build_helpdesk_workflow` e `PerRequestAgent`). Guardá-los aqui é o que permite um
        # executor do workflow emitir o evento de fontes sem refazer a busca — e refazer a busca
        # para desenhar a tela custaria uma segunda chamada ao serviço por resposta.
        self.ultimos_documentos = list(docs)
        if not docs:
            return
        corpo = "\n\n".join(
            f"[{d['index']}] {d['source']}:\n{d.get('snippet', '')}" for d in docs
        )
        context.extend_instructions(
            self.source_id, f"{SYNTHESIS_DIRECTIVE}\n\n=== DOCUMENTOS ===\n{corpo}"
        )

    async def after_run(self, *, agent, session, context, state) -> None:  # type: ignore[override]
        """Grava a contagem de referências desta resposta.

        Só as referências: o token vem do `ChatMiddleware` da fábrica de cliente, que já mede toda
        chamada de modelo. Contar de novo aqui somaria duas vezes.
        """
        from app.modules.conversations.public import (
            conversation_user,
            current_conversation,
            record_usage,
        )

        quantas = int(state.get("referencias", 0) or 0)
        atual = current_conversation()
        if not quantas or atual is None:
            return
        record_usage(conversation_user(), atual[0], atual[1], 0, 0, quantas)
