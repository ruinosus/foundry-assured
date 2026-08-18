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
