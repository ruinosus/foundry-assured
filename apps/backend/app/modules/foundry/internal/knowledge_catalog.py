"""Catálogo de bases de conhecimento — leitura, via SDK oficial.

MÁXIMA MAIOR: gestão de base de conhecimento já é recurso. `SearchIndexClient` traz as 11
operações (`list/get/create/create_or_update/delete` para base e para fonte, mais
`get_knowledge_source_status`), então este módulo não implementa gestão — projeta o que o
SDK devolve para a forma que a interface consome.

POR QUE ISTO NÃO MORA EM `app/modules/knowledge/`. São dois negócios diferentes com a mesma
palavra. `modules/knowledge/` é o PIPELINE que constrói as bases do showcase (ingest, wiki
builder, ACL, busca segura) — código nosso que roda para produzir conteúdo. Este arquivo é a
superfície de GESTÃO que o usuário final opera sem abrir o portal, a mesma natureza do
`/agents` ao lado. Se um dia a gestão virar o assunto principal, o módulo pede outro nome —
mas juntar pipeline com catálogo agora misturaria duas coisas que mudam por razões distintas.

Verificado contra o SDK INSTALADO (RULE #1): os campos abaixo saem de `KnowledgeBase`,
`KnowledgeSource` e `KnowledgeSourceStatus._attribute_map`, não da documentação.
"""

from __future__ import annotations

import contextlib
import os
from typing import Any

from app.modules.tenancy.public import tenant_config

# As operações de knowledge são preview e a versão da API decide se existem. O default segue o
# mesmo valor que o pipeline de ingestão usa — divergir faria o catálogo enxergar um conjunto de
# recursos diferente do que a ingestão cria, que é o tipo de inconsistência que ninguém desconfia.
_API_VERSION = os.environ.get("SEARCH_API_VERSION", "2026-05-01-preview")


def _client():
    """Cliente do Search, autenticado pela identidade da aplicação (RULE #2 — sem chave)."""
    from azure.identity import DefaultAzureCredential
    from azure.search.documents.indexes import SearchIndexClient

    return SearchIndexClient(
        endpoint=tenant_config().azure_search_endpoint,
        credential=DefaultAzureCredential(),
        api_version=_API_VERSION,
    )


def _iso(value: Any) -> Any:
    return value.isoformat() if hasattr(value, "isoformat") else value


def _state_name(state: Any) -> str | None:
    """Nome do estado, quando há um."""
    return (str(state) or None) if state else None


def _run(state: Any) -> dict | None:
    """A última sincronização, com os campos que respondem "esta base está atualizada?".

    Chamar `str()` neste objeto devolveria o dict do SDK serializado — `{'additional_properties':
    {'errors': []}, 'start_time': datetime.datetime(...)}` — que atravessa o JSON como texto e
    chega ilegível na tela. Foi o que a primeira chamada contra o serviço real mostrou, e é o
    tipo de defeito que só aparece com dado de verdade: com o objeto vazio, `str()` parecia bem.
    """
    if state is None:
        return None
    errors = (getattr(state, "additional_properties", None) or {}).get("errors") or []
    return {
        "started_at": _iso(getattr(state, "start_time", None)),
        "ended_at": _iso(getattr(state, "end_time", None)),
        "processed": getattr(state, "items_updates_processed", None),
        "failed": getattr(state, "items_updates_failed", None),
        "skipped": getattr(state, "items_skipped", None),
        # Contagem, não o conteúdo: mensagem de erro do indexador pode carregar caminho e nome
        # de documento, e isto é resposta de API lida por quem não necessariamente alcança a fonte.
        "error_count": len(errors),
    }


def _project_source(source: Any) -> dict:
    """Uma fonte na forma que a interface consome.

    `kind` é o que diferencia Blob de SharePoint, OneLake e Web — é a informação que decide o
    que a tela de detalhe pode oferecer, então sobe achatado em vez de ficar num enum aninhado.
    """
    return {
        "name": getattr(source, "name", None),
        "description": getattr(source, "description", None),
        "kind": str(getattr(source, "kind", "") or "") or None,
    }


def _project_base(base: Any) -> dict:
    """Uma base na forma que a interface consome — não o objeto de plataforma.

    `encryption_key`, `e_tag` e os parâmetros de raciocínio (`retrieval_reasoning_effort`,
    `output_mode`) ficam fora: são vocabulário de quem opera o serviço. O que o usuário final
    precisa saber é o nome, o que a base é, e de quais fontes ela se alimenta.
    """
    refs = getattr(base, "knowledge_sources", None) or []
    return {
        "name": getattr(base, "name", None),
        "description": getattr(base, "description", None),
        # A base REFERENCIA fontes; o nome da referência é o que liga uma coisa à outra na tela.
        "sources": [getattr(r, "name", None) for r in refs if getattr(r, "name", None)],
        "source_count": len(refs),
    }


def list_knowledge(limit: int = 50) -> dict:
    """As bases e as fontes do serviço, projetadas.

    Devolve as duas listas numa só resposta porque a tela mostra as duas juntas: uma base sem
    fonte é uma base que não responde nada, e uma fonte órfã é custo rodando sem uso. Separar
    em dois endpoints obrigaria a interface a fazer duas chamadas para render uma página.

    `limit` é o teto do que devolvemos, não o da chamada — o SDK devolve iterador que continua
    sozinho. Parar cedo é decisão nossa, e o teto fica documentado em vez de silencioso.
    """
    client = _client()
    try:
        bases: list[dict] = []
        for item in client.list_knowledge_bases():
            bases.append(_project_base(item))
            if len(bases) >= limit:
                break

        sources: list[dict] = []
        for item in client.list_knowledge_sources():
            sources.append(_project_source(item))
            if len(sources) >= limit:
                break

        # Fonte que nenhuma base referencia: custo rodando sem ninguém consultando. Marcar aqui
        # é mais honesto que deixar a interface deduzir cruzando as duas listas por conta própria.
        referenced = {s for b in bases for s in b["sources"]}
        for s in sources:
            s["orphan"] = s["name"] not in referenced

        return {"bases": bases, "sources": sources}
    finally:
        with contextlib.suppress(Exception):
            client.close()


def get_knowledge(name: str) -> dict:
    """Uma base pelo nome, com o status de sincronização de cada fonte que ela usa.

    O status é a pergunta que a tela de detalhe existe para responder — "esta base está
    atualizada?" — e ele NÃO vem no objeto da base: é uma chamada por fonte
    (`get_knowledge_source_status`). Falha de status não derruba a resposta: uma fonte que o
    serviço não sabe informar aparece como `null` e a base continua legível, porque perder a
    página inteira por causa de um campo seria pior que mostrar a página com uma lacuna visível.
    """
    client = _client()
    try:
        base = _project_base(client.get_knowledge_base(name))
        statuses = []
        for source_name in base["sources"]:
            try:
                st = client.get_knowledge_source_status(source_name)
                stats = getattr(st, "statistics", None)
                statuses.append(
                    {
                        "source": source_name,
                        # Só existe enquanto uma sincronização está EM CURSO; ausente é o caso
                        # normal (a última terminou), não um erro.
                        "state": _state_name(getattr(st, "current_synchronization_state", None)),
                        "last_run": _run(getattr(st, "last_synchronization_state", None)),
                        "interval": str(getattr(st, "synchronization_interval", "") or "") or None,
                        "total_synchronizations": getattr(stats, "total_synchronization", None),
                        "avg_items": getattr(
                            stats, "average_items_processed_per_synchronization", None
                        ),
                    }
                )
            except Exception:  # noqa: BLE001 — a base vale mais que o status de uma fonte
                statuses.append({"source": source_name, "state": None, "unavailable": True})
        base["status"] = statuses
        return base
    finally:
        with contextlib.suppress(Exception):
            client.close()
