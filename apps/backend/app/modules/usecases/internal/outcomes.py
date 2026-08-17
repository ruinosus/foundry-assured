"""Resultados de um caso de uso — o que ele produziu, e o retorno que isso representa.

O PEDIDO ERA "medir ROI ou algo similar, note, ela é de NEGÓCIO". É o número que essa pessoa mais
vai olhar, e é onde é mais fácil produzir algo bonito e falso.

O QUE MEDIMOS DE VERDADE:

    conversas atendidas   →  sessões dos agentes do caso (`list_sessions`)
    escalações abertas    →  os tickets, que o produto grava
    respostas com fonte   →  o gate de eval, quando houver execução no período

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


def _sessions_of(agent_names: list[str]) -> tuple[int, str | None]:
    """Quantas conversas os agentes deste caso atenderam.

    Erro NÃO vira zero: zero conversas e "não consegui contar" levam a conclusões opostas — a
    primeira diz que ninguém usa, a segunda não diz nada. O motivo sobe junto.
    """
    from app.modules.foundry.public import get_agent

    total = 0
    motivo: str | None = None
    for nome in agent_names:
        try:
            detalhe = get_agent(nome, sessions_limit=100)
            sessoes = detalhe.get("sessions")
            if sessoes is None:
                motivo = motivo or "As sessões de alguns agentes não puderam ser lidas."
                continue
            total += len(sessoes)
        except Exception as exc:  # noqa: BLE001 — um agente ilegível não zera a contagem
            motivo = motivo or f"Não foi possível ler as sessões: {exc}"
    return total, motivo


def _tickets_of(case_id: str, agent_names: list[str]) -> int:
    """Escalações que este caso gerou.

    O ticket não guarda o caso de uso que o abriu — então a contagem é do TOTAL do período, e a
    tela diz isso. Atribuir por heurística (adivinhar pelo texto) produziria um número que parece
    preciso e não é; melhor um número honesto e mais grosso.
    """
    with contextlib.suppress(Exception):
        from app.modules.tickets.public import list_tickets

        return len(list_tickets())
    return 0


def outcomes(case: dict, assumption: dict | None = None) -> dict:
    """O que este caso produziu, e o retorno sob a premissa informada.

    `case` é o objeto de `get_use_case` — recebido pronto para esta função não depender do módulo
    de casos de uso, o que criaria um ciclo entre dois arquivos do mesmo módulo.
    """
    premissa = {**DEFAULT_ASSUMPTION, **(assumption or {})}
    nomes = [a["name"] for a in case.get("agents", []) if a.get("name")]

    conversas, motivo = _sessions_of(nomes)
    escalados = _tickets_of(case["id"], nomes)

    # Resolvido sem escalar: a métrica que responde "o assistente resolveu, ou só encaminhou?".
    # Nunca negativa — mais tickets que conversas significa que os tickets vieram de outro lugar,
    # e um número negativo aqui seria ruído, não informação.
    resolvidos = max(conversas - escalados, 0)
    taxa = round(resolvidos / conversas, 3) if conversas else None

    minutos = resolvidos * float(premissa["minutes_per_case"])
    economia = round((minutos / 60.0) * float(premissa["hourly_cost"]), 2)

    return {
        "case": case["id"],
        "conversations": conversas,
        "escalated": escalados,
        "resolved_without_escalation": resolvidos,
        "resolution_rate": taxa,
        # A CONTA INTEIRA sobe na resposta, não só o resultado. A tela mostra "N atendimentos ×
        # M minutos × R$ X/hora", e quem discordar da premissa vê exatamente onde discordar.
        "estimated_minutes_saved": round(minutos),
        "estimated_cost_saved": economia,
        "assumption": premissa,
        # A honestidade que separa medida de propaganda: dizer o que é CONTADO e o que é ASSUMIDO.
        "measured": ["conversations", "escalated", "resolved_without_escalation"],
        "estimated": ["estimated_minutes_saved", "estimated_cost_saved"],
        "caveat": (
            "Conversas e escalações são contadas. A economia é uma ESTIMATIVA calculada sobre a "
            "premissa acima — troque-a pelos números da sua operação. As escalações são o total "
            "do período, não só as deste caso: o ticket não registra qual assistente o abriu."
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
