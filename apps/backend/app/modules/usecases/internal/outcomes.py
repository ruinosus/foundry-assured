"""Resultados de um caso de uso — o que ele produziu, e o retorno que isso representa.

O PEDIDO ERA "medir ROI ou algo similar, note, ela é de NEGÓCIO". É o número que essa pessoa mais
vai olhar, e é onde é mais fácil produzir algo bonito e falso.

O QUE MEDIMOS DE VERDADE:

    conversas atendidas   →  o store de conversas (+ sessões do Foundry, quando houver)
    tokens gastos         →  o uso que o serviço devolve no fim de cada stream
    escalações abertas    →  os tickets, que o produto grava
    respostas com fonte   →  o gate de eval, quando houver execução no período

A primeira linha já foi `list_sessions` e SÓ isso — e media nada: o runtime executa aqui, não no
Foundry, então eram zero sessões e portanto R$ 0,00 de economia em qualquer cenário. Ver
`_sessions_of`.

O QUE NÃO TEMOS, e sem o que "ROI" seria ficção: a LINHA DE BASE. Quanto tempo um atendimento
levava antes, quantos desses teriam virado ticket sem o assistente, quanto custa a hora de quem
foi poupado. Nada disso está em lugar nenhum deste sistema, e inventar um valor plausível
produziria um número com aparência de medida.

A SAÍDA: o retorno é calculado sobre uma premissa que a EMPRESA informa (`minutos por
atendimento`, `custo da hora`), e a resposta devolve a premissa junto com o número. Quem lê vê a
conta inteira. **Um ROI cuja premissa está visível é útil; um que a esconde é propaganda** — e a
diferença entre os dois é só se a premissa aparece na tela.
"""

from __future__ import annotations

import contextlib
from typing import Any

#: Premissa default — usada quando a empresa ainda não informou a dela.
#:
#: Os números são deliberadamente CONSERVADORES e estão aqui para serem substituídos: 15 minutos
#: por atendimento de suporte interno e R$ 90/hora são plausíveis e baixos. Um default otimista
#: inflaria o retorno de quem nunca abrir a configuração, que é justamente quem menos vai
#: questionar o número.
DEFAULT_ASSUMPTION = {
    "minutes_per_case": 15,
    "hourly_cost": 90.0,
    "currency": "BRL",
    "source": "default",
}


def _sessions_of(case_id: str, agent_names: list[str]) -> tuple[int, int, int, str | None]:
    """Conversas e tokens deste caso: `(conversas, tokens_in, tokens_out, motivo)`.

    ISTO ESTAVA MEDINDO NADA. A versão anterior contava só `list_sessions` dos agentes
    publicados, e uma medição contra o projeto real mostrou **zero sessões nos 10 agentes** —
    porque o runtime executa aqui, não no Foundry (`grounded/internal/per_request.py`:
    `use_service_session=False`). Com conversas sempre zero, `resolvidos` era zero e a economia
    estimada era R$ 0,00 em qualquer cenário. O painel parecia funcionar.

    Agora a fonte primária é o STORE DE CONVERSAS, que é onde as conversas de fato acontecem, e
    as sessões do Foundry continuam somando por cima — para o dia em que um agente hospedado
    atender. As duas origens não se sobrepõem: nenhuma conversa nossa vira sessão do serviço.

    Erro NÃO vira zero: zero conversas e "não consegui contar" levam a conclusões opostas — a
    primeira diz que ninguém usa, a segunda não diz nada. O motivo sobe junto.
    """
    from app.modules.conversations.public import usage_totals

    motivo: str | None = None

    # O caso de uso é a chave do store: o `record_turn`/HistoryProvider grava sob o id do
    # DOMÍNIO, que é o mesmo id do caso para os casos de um domínio só.
    totais = usage_totals(case_id)
    if totais.get("error"):
        motivo = "Não foi possível ler as conversas gravadas."
    conversas = int(totais.get("conversations", 0))
    tokens_in = int(totais.get("input_tokens", 0))
    tokens_out = int(totais.get("output_tokens", 0))

    from app.modules.foundry.public import get_agent

    for nome in agent_names:
        try:
            detalhe = get_agent(nome, sessions_limit=100)
            sessoes = detalhe.get("sessions")
            if sessoes is None:
                continue  # sem permissão para ler sessões não é falha de medição hoje
            conversas += len(sessoes)
        except Exception as exc:  # noqa: BLE001 — um agente ilegível não zera a contagem
            motivo = motivo or f"Não foi possível ler as sessões do Foundry: {exc}"
    return conversas, tokens_in, tokens_out, motivo


def _modelo() -> str:
    """O modelo que atende os domínios — é dele que sai o preço por token.

    Vem da config do TENANT, não de uma constante: em `shared` cada cliente pode ter o seu, e um
    preço fixo aqui cobraria de todos pelo modelo de um. Falhar cai num nome vazio, e o preço de
    modelo desconhecido em `cost.py` é o CONSERVADOR (o mais caro) — errar superestima o custo em
    vez de escondê-lo, que é o lado certo para errar num painel de retorno.
    """
    with contextlib.suppress(Exception):
        from app.modules.tenancy.public import tenant_config

        return tenant_config().foundry_model or ""
    return ""


def _tickets_of(case_id: str, agent_names: list[str]) -> int:
    """Escalações que ESTE caso gerou.

    O chamado passou a gravar o domínio que o abriu, então a contagem é dele — não mais o total
    do período. Antes, três chamados de plantão zeravam o resultado do helpdesk: `resolvidos` é
    `conversas - escalações`, e escalações de outro assistente comiam as conversas deste.

    Chamado ANTIGO, gravado antes do campo existir, não entra em contagem nenhuma. É o preço de
    não adivinhar: incluí-lo em todos os casos inflaria a escalação de cada um.
    """
    with contextlib.suppress(Exception):
        from app.modules.tickets.public import list_tickets

        return len(list_tickets(limit=10_000, domain=case_id))
    return 0


def outcomes(case: dict, assumption: dict | None = None) -> dict:
    """O que este caso produziu, e o retorno sob a premissa informada.

    `case` é o objeto de `get_use_case` — recebido pronto para esta função não depender do módulo
    de casos de uso, o que criaria um ciclo entre dois arquivos do mesmo módulo.
    """
    premissa = {**DEFAULT_ASSUMPTION, **(assumption or {})}
    nomes = [a["name"] for a in case.get("agents", []) if a.get("name")]

    conversas, tokens_in, tokens_out, motivo = _sessions_of(case["id"], nomes)
    escalados = _tickets_of(case["id"], nomes)

    # Resolvido sem escalar: a métrica que responde "o assistente resolveu, ou só encaminhou?".
    # Nunca negativa — mais tickets que conversas significa que os tickets vieram de outro lugar,
    # e um número negativo aqui seria ruído, não informação.
    resolvidos = max(conversas - escalados, 0)
    taxa = round(resolvidos / conversas, 3) if conversas else None

    minutos = resolvidos * float(premissa["minutes_per_case"])
    economia = round((minutos / 60.0) * float(premissa["hourly_cost"]), 2)

    # CUSTO REAL — a terceira faixa, e a única que não depende de premissa nenhuma. Tokens são
    # medidos exatamente (o serviço devolve o uso no evento final do stream); o PREÇO por 1M é
    # tabela editável, e `cost.py` diz isso no cabeçalho. Sem esta linha o painel só mostrava
    # ganho, o que faz qualquer projeto parecer lucrativo.
    from app.shared.telemetry.cost import price_for, usd_brl

    preco_in, preco_out = price_for(_modelo())
    custo_usd = tokens_in / 1e6 * preco_in + tokens_out / 1e6 * preco_out
    custo = round(custo_usd * usd_brl(), 2)

    return {
        "case": case["id"],
        "conversations": conversas,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        "actual_cost": custo,
        # O retorno LÍQUIDO. Pode ser negativo, e um número negativo aqui é informação — significa
        # que este caso gastou mais em modelo do que economizou sob a premissa informada.
        "net_saved": round(economia - custo, 2),
        "escalated": escalados,
        "resolved_without_escalation": resolvidos,
        "resolution_rate": taxa,
        # A CONTA INTEIRA sobe na resposta, não só o resultado. A tela mostra "N atendimentos ×
        # M minutos × R$ X/hora", e quem discordar da premissa vê exatamente onde discordar.
        "estimated_minutes_saved": round(minutos),
        "estimated_cost_saved": economia,
        "assumption": premissa,
        # A honestidade que separa medida de propaganda: dizer o que é CONTADO e o que é ASSUMIDO.
        "measured": [
            "conversations", "escalated", "resolved_without_escalation",
            # Tokens são MEDIDOS. O preço por token é tabela — por isso `actual_cost` fica numa
            # faixa própria na tela, nem com o contado nem com o estimado.
            "input_tokens", "output_tokens",
        ],
        "estimated": ["estimated_minutes_saved", "estimated_cost_saved", "net_saved"],
        "caveat": (
            "Conversas e escalações são contadas. A economia é uma ESTIMATIVA calculada sobre a "
            "premissa acima — troque-a pelos números da sua operação. O custo é medido em "
            "tokens reais, convertido por uma tabela de preços editável. Escalações abertas "
            "antes de o chamado passar a registrar o assistente de origem não entram em "
            "contagem nenhuma."
        ),
        "reason": motivo,
    }


def parse_assumption(body: dict[str, Any]) -> dict:
    """Valida a premissa informada. Número absurdo é recusado, não usado.

    Sem isto, 10000 minutos por atendimento produziria uma economia de milhões — e o número
    apareceria na tela com a mesma cara de qualquer outro. Um limite explícito é o que impede a
    ferramenta de ser usada para fabricar um resultado.
    """
    minutos = body.get("minutes_per_case", DEFAULT_ASSUMPTION["minutes_per_case"])
    custo = body.get("hourly_cost", DEFAULT_ASSUMPTION["hourly_cost"])
    try:
        minutos = float(minutos)
        custo = float(custo)
    except (TypeError, ValueError) as exc:
        raise ValueError("Minutos e custo por hora precisam ser números.") from exc

    if not 0 < minutos <= 480:
        raise ValueError("Minutos por atendimento deve ficar entre 1 e 480 (um dia de trabalho).")
    if not 0 < custo <= 10_000:
        raise ValueError("Custo por hora deve ser positivo e menor que 10.000.")

    return {
        "minutes_per_case": minutos,
        "hourly_cost": custo,
        "currency": str(body.get("currency") or DEFAULT_ASSUMPTION["currency"])[:8],
        "source": "informado",
    }
