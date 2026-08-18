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

A FÓRMULA NÃO É NOSSA — É A **AGENT ASSISTED HOURS** DA MICROSOFT. Este arquivo tinha um modelo
próprio (`minutos por atendimento` × `custo da hora`) que se apresentava como "deliberadamente
conservador" e não era: usava 15 minutos por atendimento contra os **6 minutos** que a Microsoft
publica COM FONTE. Éramos de 1,25× a 2,5× mais generosos que o default de terceiro, dependendo de
quantas citações a resposta trouxesse — exatamente o tipo de número que o parágrafo abaixo diz
querer evitar. Trocar por uma fórmula publicada não é só honestidade: premissa citável de terceiro
é muito mais defensável numa conversa de negócio do que premissa nossa.

    AAH = (referências de conhecimento + sessões sem referência, ponderadas) × multiplicador ÷ 60
    Agent Assisted Value = AAH × valor da hora

    · cada referência de conhecimento citada conta uma vez e vale o multiplicador;
    · sessão sem referência é ponderada pelo DESFECHO: resolvida 1.0, escalada/abandonada 0.7;
    · multiplicador default 6 min (pesquisa da Microsoft sobre recuperação de informação);
    · valor da hora default da Microsoft é US$ 72 (US BLS) — aqui fica R$ 90, que é NOSSO e
      admite ser nosso: converter US$ 72 daria ~R$ 400/h, absurdo para suporte interno no Brasil.

Repare no insumo principal: CONTAGEM DE REFERÊNCIAS. É justamente o que este produto já mede como
diferencial, e o que estava sendo jogado fora — o `grounded` calculava `sources` só para desenhar
o painel de evidência. O detector de `eval/assertions.py` responde "citou ou não", booleano que
serve de gate e não serve de conta.

A SAÍDA: a resposta devolve a premissa E A FONTE DELA junto com o número. Quem lê vê a conta
inteira e de onde cada constante veio. **Um ROI cuja premissa está visível é útil; um que a esconde
é propaganda** — e a diferença entre os dois é só se a premissa aparece na tela.

Referência: learn.microsoft.com/microsoft-copilot-studio/guidance/agent-business-value-measure-impact
"""

from __future__ import annotations

import contextlib
import os
from typing import Any


#: A premissa e a procedência vêm de `value/default.yaml` — DADO, não literal em Python.
#:
#: Estavam aqui como dicionários, e o problema não era estética: obrigava a trocar CÓDIGO para
#: trocar a premissa de uma operação, e permitia que alguém mudasse o número sem mudar a
#: procedência ao lado dele. Agora as duas coisas moram no mesmo documento, e `VALUE_MODEL`
#: aponta para outro arquivo quando a instalação tem o seu — mesma ideia do `AGENTS_DIR` para
#: prompts (ADR-014). Ver `value_model.py` e `value/default.yaml`.
def _premissa_default() -> dict:
    from app.modules.usecases.internal.value_model import assumption

    return assumption()


def _procedencia() -> dict:
    from app.modules.usecases.internal.value_model import provenance

    return provenance()


def _sessions_of(case_id: str, agent_names: list[str]) -> tuple[int, int, int, int, int, str | None]:
    """Deste caso: `(conversas, tokens_in, tokens_out, referências, conversas_com_ref, motivo)`.

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
    referencias = int(totais.get("references", 0))
    com_refs = int(totais.get("conversations_with_references", 0))

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
    return conversas, tokens_in, tokens_out, referencias, com_refs, motivo


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


def _regiao_de_preco() -> str:
    """A região cuja lista de preços consultar.

    Importa pouco na prática, e o motivo é medido: preferimos os meters de deployment **global**,
    e o preço global é o MESMO nas 27 regiões que o publicam (conferido no meter
    `GPT 5 Mini Inpt Glbl 1M Tokens`). A região só muda o número para deployment `DZone` ou
    regional — daí ser declarada por ambiente em vez de adivinhada a partir do endpoint.
    """
    return os.environ.get("AZURE_PRICE_REGION", "eastus")


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
    premissa = {**_premissa_default(), **(assumption or {})}
    nomes = [a["name"] for a in case.get("agents", []) if a.get("name")]

    conversas, tokens_in, tokens_out, referencias, com_refs, motivo = _sessions_of(
        case["id"], nomes
    )
    escalados = _tickets_of(case["id"], nomes)

    # Resolvido sem escalar: a métrica que responde "o assistente resolveu, ou só encaminhou?".
    # Nunca negativa — mais tickets que conversas significa que os tickets vieram de outro lugar,
    # e um número negativo aqui seria ruído, não informação.
    resolvidos = max(conversas - escalados, 0)
    taxa = round(resolvidos / conversas, 3) if conversas else None

    # ── Agent Assisted Hours ──────────────────────────────────────────────────────────────
    # AAH = (referências + sessões sem referência ponderadas por desfecho) × multiplicador ÷ 60
    #
    # A ponderação da Microsoft é por SESSÃO e por desfecho, e o que temos aqui são agregados:
    # total de conversas, quantas citaram, e quantas escalaram. Não existe o cruzamento "escalou E
    # não citou", então a atribuição é uma premissa — e a escolha dela importa.
    #
    # A escalação é atribuída PRIMEIRO às sessões sem referência, até esgotá-las. Duas razões, e a
    # segunda é a que decide: (1) é o comportamento mais plausível, porque escalar é mais provável
    # justamente quando nenhuma fonte foi encontrada; (2) é o LADO CONSERVADOR, porque joga
    # sessões para o peso 0.7 em vez de 1.0. A primeira versão disto prorrateava a taxa de
    # escalação uniformemente e produzia 4.700 sessões ponderadas onde o exemplo publicado dá
    # 4.400 — mais generoso que a Microsoft, que é exatamente o vício que esta mudança veio
    # eliminar. Com a atribuição por esgotamento, o exemplo publicado fecha na vírgula, e
    # `tests/usecases/aah_formula_test.py` é o gate que impede a fórmula de derivar de novo.
    sem_ref = max(conversas - com_refs, 0)
    escaladas_sem_ref = min(escalados, sem_ref)
    ponderadas = (sem_ref - escaladas_sem_ref) * float(premissa["resolved_weight"]) + (
        escaladas_sem_ref * float(premissa["unresolved_weight"])
    )
    horas = (referencias + ponderadas) * float(premissa["minutes_per_reference"]) / 60.0
    economia = round(horas * float(premissa["hourly_cost"]), 2)

    # REFERÊNCIA ZERO É AMBÍGUO, e a ambiguidade tem de ser dita. Conversa gravada antes de o
    # campo `refs` existir não tem o dado — e "esta resposta não citou nada" (que é falha de
    # fundamentação, grave) e "não sei se citou" levam a ações opostas. Sem esta linha, o painel
    # subestimaria o valor em silêncio e ainda por cima acusaria o agente de não citar.
    referencias_parciais = conversas > 0 and com_refs == 0
    if referencias_parciais:
        motivo = motivo or (
            "Nenhuma conversa deste caso tem contagem de referências gravada — as conversas "
            "anteriores a esta medição não a têm. A parcela de referências da fórmula está "
            "zerada por ausência de dado, não por ausência de citação."
        )

    # CUSTO REAL — a terceira faixa, e a única que não depende de premissa nenhuma. Tokens são
    # medidos exatamente (o serviço devolve o uso no evento final do stream); o PREÇO vem da
    # Azure. Sem esta linha o painel só mostrava ganho, o que faz qualquer projeto parecer
    # lucrativo.
    #
    # ORDEM: a lista de preços da Azure primeiro (`pricing`, que lê `prices.azure.com`), a tabela
    # de reserva do shared kernel depois, e **nada** se as duas falharem. O terceiro caso é o que
    # mudou: antes um modelo desconhecido recebia um preço "conservador" que aparecia na tela com
    # a mesma cara de um preço real. `gpt-5-pro` teria saído 12× mais barato do que é.
    from app.shared.telemetry.cost import price_for as preco_de_reserva
    from app.shared.telemetry.cost import usd_brl

    modelo = _modelo()
    preco = None
    # De QUAL meter da Azure o preço saiu. `SkuMeter` é coluna do export FOCUS de billing, e é
    # este mesmo vocabulário — então guardar o nome aqui é a chave que permite, quando houver
    # fatura com volume, cruzar o estimado contra o cobrado. Custa nada e não dá para reconstruir
    # depois.
    meters: list[str] = []
    with contextlib.suppress(Exception):
        from app.modules.pricing.public import price_detail

        detalhe = price_detail(modelo, _regiao_de_preco())
        preco, meters = detalhe["price"], detalhe["meters"]
    preco = preco or preco_de_reserva(modelo)

    if preco is None:
        custo = None
        motivo = motivo or (
            f"Não foi possível determinar o preço por token do modelo {modelo!r} — o custo não "
            "entra no cálculo. O retorno líquido abaixo conta só a economia estimada."
        )
    else:
        custo_usd = tokens_in / 1e6 * preco[0] + tokens_out / 1e6 * preco[1]
        custo = round(custo_usd * usd_brl(), 2)

    return {
        "case": case["id"],
        "conversations": conversas,
        "input_tokens": tokens_in,
        "output_tokens": tokens_out,
        # `None` significa "não sei o preço deste modelo", e a tela mostra isso — não um zero,
        # que seria indistinguível de "não gastou nada".
        "actual_cost": custo,
        # A procedência do CUSTO, do mesmo jeito que `provenance` é a procedência do valor: um
        # número de dinheiro que não diz de onde veio não é auditável.
        "price_model": modelo,
        "price_meters": meters,
        # O retorno LÍQUIDO. Pode ser negativo, e um número negativo aqui é informação — significa
        # que este caso gastou mais em modelo do que economizou sob a premissa informada.
        "net_saved": round(economia - (custo or 0.0), 2),
        "escalated": escalados,
        "resolved_without_escalation": resolvidos,
        "resolution_rate": taxa,
        # A CONTA INTEIRA sobe na resposta, não só o resultado — cada termo da AAH separado, para
        # a tela poder mostrar a fórmula e quem discordar ver exatamente onde discordar.
        "references": referencias,
        "conversations_with_references": com_refs,
        "sessions_without_references": sem_ref,
        "weighted_sessions": round(ponderadas, 1),
        "assisted_hours": round(horas, 1),
        "assisted_value": economia,
        "assumption": premissa,
        "provenance": _procedencia(),
        # Verdadeiro quando a parcela de referências está zerada por FALTA DE DADO, não por
        # ausência de citação. A tela precisa distinguir as duas para não acusar o agente.
        "references_partial": referencias_parciais,
        # A honestidade que separa medida de propaganda: dizer o que é CONTADO e o que é ASSUMIDO.
        "measured": [
            "conversations", "escalated", "resolved_without_escalation",
            # Referências citadas são CONTADAS, uma a uma, no fim de cada resposta.
            "references", "conversations_with_references",
            # Tokens são MEDIDOS. O preço por token é tabela — por isso `actual_cost` fica numa
            # faixa própria na tela, nem com o contado nem com o estimado.
            "input_tokens", "output_tokens",
        ],
        "estimated": ["weighted_sessions", "assisted_hours", "assisted_value", "net_saved"],
        "caveat": (
            "Conversas, escalações e referências citadas são contadas. As horas assistidas usam "
            "a fórmula Agent Assisted Hours da Microsoft, com o multiplicador de 6 minutos que "
            "ela publica; o valor da hora é o desta instalação. O desfecho não é gravado por "
            "conversa, então as escalações são atribuídas primeiro às sessões sem referência — a "
            "hipótese mais plausível e também a mais conservadora. O custo é medido em tokens "
            "reais, convertido "
            "por uma tabela de preços editável. Escalações abertas antes de o chamado passar a "
            "registrar o assistente de origem não entram em contagem nenhuma."
        ),
        "reason": motivo,
    }


def parse_assumption(body: dict[str, Any]) -> dict:
    """Valida a premissa informada. Número absurdo é recusado, não usado.

    Sem isto, 10000 minutos por atendimento produziria uma economia de milhões — e o número
    apareceria na tela com a mesma cara de qualquer outro. Um limite explícito é o que impede a
    ferramenta de ser usada para fabricar um resultado.
    """
    padrao = _premissa_default()
    minutos = body.get("minutes_per_reference", padrao["minutes_per_reference"])
    custo = body.get("hourly_cost", padrao["hourly_cost"])
    try:
        minutos = float(minutos)
        custo = float(custo)
    except (TypeError, ValueError) as exc:
        raise ValueError("Minutos e custo por hora precisam ser números.") from exc

    if not 0 < minutos <= 480:
        raise ValueError("Minutos por referência deve ficar entre 1 e 480 (um dia de trabalho).")
    if not 0 < custo <= 10_000:
        raise ValueError("Custo por hora deve ser positivo e menor que 10.000.")

    # Os PESOS DE DESFECHO não são configuráveis: são parte da fórmula publicada, não da premissa
    # da empresa. Deixá-los editáveis permitiria "ajustar" a AAH até o número agradar, e aí ela
    # deixa de ser a fórmula da Microsoft e volta a ser a nossa — com o crachá de outro.
    return {
        "minutes_per_reference": minutos,
        # Os pesos de desfecho NÃO vêm do corpo da requisição nem do documento: são da fórmula
        # publicada, e deixá-los editáveis permitiria "ajustar" a AAH até o número agradar.
        "resolved_weight": padrao["resolved_weight"],
        "unresolved_weight": padrao["unresolved_weight"],
        "hourly_cost": custo,
        "currency": str(body.get("currency") or padrao["currency"])[:8],
        "source": "informado",
    }
