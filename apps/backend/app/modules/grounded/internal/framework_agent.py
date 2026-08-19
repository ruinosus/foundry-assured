"""O domínio grounded como agente do framework — a alternativa ao laço de SSE escrito à mão.

O QUE ISTO SUBSTITUI, e por que só agora foi possível. `stream_grounded` escreve o próprio laço de
SSE: monta o credential OBO, chama `retrieve()`, sintetiza pela API de respostas, emite os eventos
AG-UI à mão e grava conversa e uso por chamada explícita. São 270 linhas que fazem o que o
framework faz — exceto por duas coisas que ele não fazia, e as duas foram resolvidas:

  · ACL por usuário — `AzureAISearchContextProvider` não envia `x-ms-query-source-authorization`.
    Resolvido por `GroundedRetrieval`, que embrulha o nosso `retrieve()` no `ContextProvider` do
    framework.
  · o evento de fontes — o adapter descarta `content.annotations`. Resolvido pela rota PÚBLICA do
    runtime de workflow (`ctx.add_event(WorkflowEvent("sources", ...))`), já provada no helpdesk.

E faltava uma terceira peça que eu não tinha encontrado: **`FoundryAgent`**. `FoundryChatClient` não
aceita `agent_name`, então um agente comum falaria com o DEPLOYMENT DO MODELO e não com o agente
PUBLICADO — a versão que o portal mostra deixaria de responder, que é exatamente o estado que a
SEGUNDA MÁXIMA proíbe. `FoundryAgent` aceita `agent_name` E `agent_version`, então a propriedade
não só se preserva: a versão passa a ser explícita, o que o caminho atual nem tem.

O QUE SE GANHA: histórico, uso e o adapter oficial entram por construção, em vez de por chamada
nossa. O que sobra de código é a montagem.

ATRÁS DE UMA CHAVE, e isso é deliberado. Esta é a única mudança desta série que não dá para provar
offline: ela toca OBO e ACL, e o modo de falha de errar não é "quebra" — é **servir documento que a
pessoa não deveria ver**, ou 403 silencioso. Gate nenhum pega isso sem identidade real. Então o
caminho novo nasce desligado, liga por `GROUNDED_VIA_FRAMEWORK`, e desligar é uma variável — não um
revert.
"""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


def via_framework() -> bool:
    """O caminho novo está ligado?

    Desligado por default: o caminho à mão é o único hoje verificado contra o serviço real, e
    trocar o que funciona por padrão — antes de uma conversa de verdade provar o novo — inverteria
    o ônus da prova.
    """
    return os.environ.get("GROUNDED_VIA_FRAMEWORK", "").strip().lower() in {"1", "true", "yes"}


def build_grounded_agent(domain: Any, user: Any, thread_id: str = "") -> Any:
    """Um `FoundryAgent` que responde COMO O AGENTE PUBLICADO, com ACL e histórico.

    `agent_name` é o id do domínio, igual ao que `stream_grounded` já usa — o mesmo agente, pela
    via canônica. `agent_version` fica em aberto (a mais recente) porque fixar versão aqui faria o
    republish deixar de ter efeito, que é o oposto do que a SEGUNDA MÁXIMA quer.

    O usuário é passado, não lido de contextvar: `retrieve()` precisa da identidade para trimar por
    ACL, e quem constrói está no contexto da requisição. Medido que o contextvar sobreviveria
    (`tests/grounded/contextvar_survival_test.py`), mas passar explicitamente é melhor desenho — e
    é o lado seguro para errar quando o erro é servir documento demais.
    """
    from agent_framework_foundry import FoundryAgent

    from app.modules.conversations.public import (
        build_history_provider,
        conversation_user,
    )
    from app.modules.grounded.internal.retrieval_provider import GroundedRetrieval
    from app.modules.tenancy.public import tenant_config
    from app.shared.auth import credential_for_request

    cfg = tenant_config()
    domain_id = getattr(domain, "id", "") or "grounded"

    recuperacao = GroundedRetrieval(user, domain, agent_id=domain_id)
    historico = build_history_provider(conversation_user(), domain_id, thread_id)
    providers = [p for p in (recuperacao, historico) if p is not None]

    agente = FoundryAgent(
        project_endpoint=cfg.foundry_project_endpoint or None,
        agent_name=domain_id,
        credential=credential_for_request(),
        context_providers=providers,
        # O gravador de uso DE NÍVEL DE AGENTE. `FoundryAgent` constrói o cliente por dentro, e o
        # `middleware` dele é agent-level (a docstring do pacote diz isso) — um `ChatMiddleware`
        # aqui é silenciosamente ignorado. A primeira versão deste arquivo errou nisso, e o efeito
        # foi token zerado numa conversa que gravou todo o resto.
        middleware=[_usage_middleware()],
        id=domain_id,
        name=domain_id,
        description=f"Grounded cited Q&A for the {domain_id} domain.",
    )
    # A recuperação fica alcançável para o executor que emite as fontes — ele precisa das citações
    # que ESTA requisição buscou, e refazer a busca para desenhar a tela custaria uma segunda
    # chamada ao serviço por resposta.
    agente_recuperacao(agente, recuperacao)
    return agente


def agente_recuperacao(agente: Any, recuperacao: Any = None) -> Any:
    """Guarda (ou devolve) o provider de recuperação de um agente.

    Um atributo em vez de um parâmetro no executor porque o workflow monta os dois separadamente e
    só o construtor conhece os dois ao mesmo tempo. Nome de função em vez de acesso direto para o
    acoplamento ficar visível em quem o usa.
    """
    if recuperacao is not None:
        agente._foundry_assured_retrieval = recuperacao
        return recuperacao
    return getattr(agente, "_foundry_assured_retrieval", None)


def _usage_middleware() -> Any:
    from app.modules.conversations.public import agent_usage_recorder

    return agent_usage_recorder()


def build_grounded_workflow(domain: Any, user: Any, thread_id: str = "") -> Any:
    """O agente publicado embrulhado num workflow de UM nó, para poder emitir as fontes.

    POR QUE WORKFLOW E NÃO AGENTE DIRETO. O adapter tem dois runtimes, e só o de WORKFLOW converte
    evento arbitrário em `CustomEvent` — é a rota pública que o helpdesk já usa. Um agente comum
    responderia igual, mas o painel de evidências ficaria vazio, e esse painel é a peça que mostra
    de onde cada afirmação veio.

    Um nó mais o emissor: a recuperação acontece no `before_run` do próprio agente, então as fontes
    só existem depois que ele roda. O evento sai após a resposta — mesmo comportamento do caminho à
    mão, que também emite `sources` depois do texto.
    """
    from agent_framework import WorkflowBuilder

    from app.modules.grounded.internal.sources_executor import SourcesExecutor

    agente = build_grounded_agent(domain, user, thread_id)
    fontes = SourcesExecutor(agente_recuperacao(agente), executor_id="sources")
    return (
        WorkflowBuilder(
            name=f"Grounded:{getattr(domain, 'id', 'grounded')}",
            description="Recupera com ACL, responde como o agente publicado, e emite as fontes.",
            start_executor=agente,
        )
        .add_chain([agente, fontes])
        .build()
    )


async def mount_grounded_via_framework(request: Any, domain: Any, domain_id: str) -> Any:
    """Serve o domínio grounded pelo workflow do framework, em AG-UI.

    Usa o adapter OFICIAL (`AgentFrameworkWorkflow` + `run_workflow_stream`) em vez de reencodar
    eventos à mão — é justamente isso que a troca compra. O corpo e o usuário são lidos aqui, no
    contexto da requisição, pelo mesmo desenho do caminho antigo.
    """
    from fastapi.responses import StreamingResponse

    from app.shared.auth import current_user

    corpo = await request.json()
    thread_id = str(corpo.get("threadId") or corpo.get("thread_id") or "")
    fluxo = build_grounded_workflow(domain, current_user(), thread_id)

    from ag_ui.encoder import EventEncoder
    from agent_framework_ag_ui import AgentFrameworkWorkflow

    adaptado = AgentFrameworkWorkflow(workflow=fluxo, name=domain_id)

    async def sse():
        # `run()` devolve OBJETOS `BaseEvent`, não SSE já codificado — quem monta o endpoint pelo
        # helper do pacote nem vê isso, porque ele encoda por dentro. Montando à mão, esquecer o
        # encoder faria o `StreamingResponse` serializar repr de objeto Python: a resposta sai com
        # 200 e o cliente não entende nada.
        enc = EventEncoder()
        async for evento in adaptado.run(corpo):
            yield enc.encode(evento)

    return StreamingResponse(sse(), media_type="text/event-stream")
