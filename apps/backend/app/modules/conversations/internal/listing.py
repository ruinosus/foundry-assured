"""A lista de conversas — a nossa mais as que o Foundry já tem.

O PEDIDO que gerou este arquivo: *"queria que os que forem feitos/salvos no azure conseguíssemos
usar"*. Um agente executado pelo Foundry produz uma sessão LÁ, e essa sessão é real mesmo que o
nosso store nunca a tenha visto. Ignorá-la faria a tela mentir por omissão — a conversa existe, e
o usuário não a encontraria.

As duas origens não competem, elas se completam:

    agente executa AQUI    →  blob de apêndice no nosso store   (transcrição completa)
    agente executa NO FOUNDRY →  `list_sessions` do serviço      (id, status, timestamps)

A diferença aparece na resposta, no campo `source`. É a mesma regra da SEGUNDA MÁXIMA aplicada à
conversa: um item que mente sobre onde executa é pior que um item ausente. A sessão do Foundry
não traz o texto — `AgentSessionResource` tem só id, status e timestamps, nenhum conteúdo — então
ela entra na lista como retomável pelo serviço, não como transcrição que temos.

Hoje o serviço devolve zero sessões (medido: 10 agentes, 0 sessões), porque nada nosso executa
por lá ainda. Esta função já lê as duas para que, no dia em que um hosted agent for usado, a
conversa apareça sem ninguém precisar lembrar de mexer aqui.
"""

from __future__ import annotations

import contextlib
from dataclasses import asdict

from app.modules.conversations.internal.store import store


def list_conversations(user_id: str, agent: str = "") -> list[dict]:
    """As conversas do usuário, mais recentes primeiro, opcionalmente de um agente só."""
    nossas = [
        {**asdict(c), "source": "backend", "resumable": True}
        for c in store().list(user_id, agent)
    ]

    vistas = {c["id"] for c in nossas}
    for sessao in _foundry_sessions(agent):
        if sessao["id"] not in vistas:
            nossas.append(sessao)

    return sorted(nossas, key=lambda c: c.get("updated_at") or "", reverse=True)


def _foundry_sessions(agent: str) -> list[dict]:
    """Sessões que o Foundry guarda para um agente executado por ele.

    Sem `agent` não há o que perguntar: `list_sessions` é por agente, e varrer todos os agentes
    publicados a cada abertura da lista custaria uma chamada por agente para devolver, hoje, zero.

    Falha aqui não derruba a lista — as conversas nossas continuam aparecendo.
    """
    if not agent:
        return []

    saida: list[dict] = []
    with contextlib.suppress(Exception):
        from app.modules.foundry.public import get_agent

        detalhe = get_agent(agent, sessions_limit=50)
        for s in detalhe.get("sessions") or []:
            ident = s.get("id") or s.get("agent_session_id")
            if not ident:
                continue
            saida.append(
                {
                    "id": ident,
                    "agent": agent,
                    # O serviço não guarda o texto, então não há primeira pergunta para mostrar.
                    # Título vazio é honesto; inventar "Conversa de <data>" fingiria conteúdo.
                    "title": "",
                    "updated_at": s.get("last_accessed_at") or s.get("created_at") or "",
                    "messages": 0,
                    "foundry_session_id": ident,
                    "source": "foundry",
                    # Retomável PELO SERVIÇO: quem executa a sessão é o Foundry, não nós.
                    "resumable": True,
                }
            )
    return saida


def record_turn(
    user_id: str,
    agent: str,
    conversation_id: str,
    user_text: str,
    assistant_text: str,
    *,
    citations: list[dict] | None = None,
) -> None:
    """Grava um turno onde NÃO há agente do framework para carregar um `HistoryProvider`.

    Os domínios grounded (cockpit, techdocs, selfwiki) não constroem um agente do
    `agent_framework`: chamam `responses.create()` direto no cliente do Foundry. Sem agente não há
    `context_providers`, e portanto não há onde plugar o provider — então o turno é gravado aqui,
    explicitamente, com o mesmo formato de mensagem para que a leitura seja uma só.

    Duas mecânicas para a mesma coisa é um cheiro, e este é honesto: reflete que metade dos
    domínios usa a abstração de agente do framework e a outra metade fala com a API de respostas.
    Se um dia o grounded virar agente do framework, esta função sai e o provider cobre os dois.

    Falha não propaga: perder o registro de uma conversa é ruim, perder a RESPOSTA que o usuário
    já leu por causa do registro seria pior.
    """
    if not (user_id and conversation_id):
        return
    linhas = []
    if user_text:
        linhas.append({"role": "user", "text": user_text})
    if assistant_text:
        # A EVIDÊNCIA VIAJA COM A RESPOSTA. Sem isto, recarregar a página apagava a fonte de
        # toda a conversa — a citação vivia só como evento ao vivo. Guardamos título, url,
        # índice e o trecho que JÁ saiu na resposta; nunca o documento. O direito de ler o
        # documento é verificado no clique (rota /source), nunca herdado daqui.
        #
        # `keyword-only` com default None para que os chamadores existentes não mudem, e a
        # chave só existe quando há citação — mensagem sem fonte continua byte-idêntica.
        mensagem = {"role": "assistant", "text": assistant_text}
        if citations:
            mensagem["annotations"] = citations
        linhas.append(mensagem)
    if not linhas:
        return
    with contextlib.suppress(Exception):
        store().append(user_id, agent, conversation_id, linhas)


def get_conversation(user_id: str, agent: str, conversation_id: str) -> list[dict]:
    """As mensagens de uma conversa nossa, no formato do framework (`Message.to_dict()`).

    Escopo por usuário é o controle de acesso: o caminho do blob começa no object-id de quem
    pediu, então não existe consulta que alcance a conversa de outra pessoa.
    """
    return store().read(user_id, agent, conversation_id)


def record_usage(
    user_id: str,
    agent: str,
    conversation_id: str,
    incoming: int,
    outgoing: int,
    references: int = 0,
) -> None:
    """Soma tokens e referências de conhecimento desta conversa.

    `references` é o número de fontes citadas na resposta — insumo da fórmula Agent Assisted
    Hours. Silencioso em falha: contabilidade não derruba chat.
    """
    if not (user_id and conversation_id):
        return
    with contextlib.suppress(Exception):
        store().add_usage(user_id, agent, conversation_id, incoming, outgoing, references)


def usage_totals(agent: str = "") -> dict:
    """Conversas e tokens de TODOS os usuários — a entrada de custo real do painel de ROI."""
    try:
        return store().totals(agent)
    except Exception:  # noqa: BLE001 — o painel mostra "não foi possível medir", não um zero falso
        return {
            "conversations": 0,
            "input_tokens": 0,
            "output_tokens": 0,
            "references": 0,
            "conversations_with_references": 0,
            "error": True,
        }


def find_conversation(user_id: str, conversation_id: str) -> dict:
    """A conversa pelo ID, sem saber o agente. `{agent, messages}` — vazio se não houver.

    POR QUE ESTE RECORTE EXISTE. O `connect` do CopilotKit conhece só o `threadId`: o
    `AgentRunnerConnectRequest` tem `threadId` e `headers`, e mais nada. Sem esta função, reidratar
    uma conversa a partir do runtime exigiria adivinhar o agente pela URL — o que quebraria no dia
    em que a mesma conversa fosse aberta de outro lugar.

    A varredura é sobre as conversas DO USUÁRIO, o que também é o controle de acesso: um id de
    outra pessoa simplesmente não aparece na lista dela.
    """
    alvo = (conversation_id or "").strip()
    if not (user_id and alvo):
        return {}
    for meta in store().list(user_id):
        if meta.id == alvo:
            return {"agent": meta.agent, "messages": store().read(user_id, meta.agent, alvo)}
    return {}
