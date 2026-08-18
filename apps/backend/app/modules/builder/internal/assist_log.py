"""O desfecho de uma proposta do assistente de tela — e o que se mede com ele.

POR QUE ISTO EXISTE. O `builder` não é caso de uso de negócio: ele não atende cliente, ele ajuda
alguém a preencher um formulário. Mas é trabalho de agente, custa token e pode estar ajudando mal
— e nada disso tinha resposta, porque aceitar ou descartar uma proposta era ação só de tela.

O QUE SE MEDE, e por que estas três e não "quantas vezes foi usado":

    aceita      a proposta virou o texto como veio
    editada     virou texto DEPOIS de a pessoa corrigir  ← o sinal de qualidade que importa
    descartada  não virou nada

A taxa de aproveitamento (aceitas + editadas) diz se o assistente serve. A proporção de EDITADAS
diz se ele acerta o suficiente para não dar trabalho — um assistente com 90% de aproveitamento e
80% de edição está sendo tolerado, não usado. Essa é a distinção que "quantas vezes foi usado"
apaga.

POR QUE O REGISTRO VEM DO NAVEGADOR, contrariando a regra do módulo de auditoria de que eventos
entram pelos módulos que os produzem e nunca por HTTP. Aqui a decisão ACONTECE no navegador: não
há chamada de serviço quando alguém clica em "Descartar". A porta é estreita de propósito — tipo e
escopo fixos, desfecho de uma lista fechada, sem resumo livre — para que ela registre este fato e
nada mais. Uma rota que aceitasse evento arbitrário deixaria a trilha fabricável.
"""

from __future__ import annotations

#: Os desfechos possíveis. Fechado: um verbo livre aqui viraria uma métrica que ninguém consegue
#: interpretar seis meses depois.
DESFECHOS = ("accepted", "edited", "discarded")


class InvalidOutcome(ValueError):
    """Desfecho fora da lista — recusado antes de virar evento."""


def record_proposal(
    resource: str, field: str, outcome: str, sources: list[str] | None = None, chars: int = 0
) -> dict:
    """Registra o desfecho de UMA proposta.

    O TEXTO da proposta não entra — nem o aceito, nem o corrigido. Ele é conteúdo, e a trilha é
    imutável; o que se mede aqui é o desfecho, não o que foi escrito. O tamanho entra, porque
    responde "era um campo curto ou um prompt inteiro" sem guardar nenhum dos dois.
    """
    from app.modules.audit.public import actor, actor_detail, record

    if outcome not in DESFECHOS:
        raise InvalidOutcome(f"desfecho '{outcome}' não existe (use: {', '.join(DESFECHOS)})")

    return record(
        scope="assist",
        actor=actor(),
        kind="assist",
        summary=f"proposta {outcome} em {field or '?'}",
        ref=str(resource or "")[:63],
        detail={
            "field": str(field or "")[:63],
            "outcome": outcome,
            # As FONTES declaradas pelo agente. É o que liga a medição à procedência: dá para
            # perguntar se proposta com fonte é mais aceita que proposta sem.
            "sources": [str(s)[:120] for s in (sources or [])][:20],
            "chars": max(int(chars or 0), 0),
            **actor_detail(),
        },
    )


def stats() -> dict:
    """Os números do assistente, a partir da trilha. Sem tabela paralela.

    Ler da trilha em vez de manter um contador é o que garante que o número da tela e o evento
    auditável nunca divergem — um contador é uma segunda verdade, e a primeira divergência não dá
    erro, só faz a tela mentir.
    """
    from app.modules.audit.public import read

    eventos = [e for e in read("assist") if (e.get("detail") or {}).get("outcome")]
    por_desfecho = {d: 0 for d in DESFECHOS}
    com_fonte = 0
    campos: dict[str, int] = {}

    for e in eventos:
        d = e["detail"]
        por_desfecho[d["outcome"]] = por_desfecho.get(d["outcome"], 0) + 1
        if d.get("sources"):
            com_fonte += 1
        campo = d.get("field") or "?"
        campos[campo] = campos.get(campo, 0) + 1

    total = len(eventos)
    usadas = por_desfecho["accepted"] + por_desfecho["edited"]
    return {
        "total": total,
        "by_outcome": por_desfecho,
        # Aproveitamento = virou texto. Edição = precisou de conserto. As duas juntas, porque uma
        # sozinha engana: 100% de aproveitamento com 90% de edição é um assistente tolerado.
        "used_rate": round(usadas / total, 3) if total else None,
        "edited_rate": round(por_desfecho["edited"] / usadas, 3) if usadas else None,
        "with_sources": com_fonte,
        "by_field": dict(sorted(campos.items(), key=lambda kv: -kv[1])[:10]),
    }
