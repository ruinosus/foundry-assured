"""Path B da ADR-022 — a otimização de agente é do Foundry; nós só mostramos.

O QUE FOI MEDIDO, e por isso este arquivo é fino. Citando o pacote instalado:

    OptimizationJob — "a long-running job that optimizes an agent's configuration (instructions,
    model, skills, tools) to maximize evaluation scores. On success, the result contains scored
    candidates."

Melhorar um agente existente já é capacidade de primeira parte, e é PONTUADA contra avaliação em
vez de afirmada. Escrever aqui um segundo laço de melhoria de prompt daria um resultado
não-pontuado — preferência apresentada como fato. Então não escrevemos: disparamos o job e
renderizamos os candidatos.

E a Microsoft traçou a mesma fronteira que esta ADR precisa: `OptimizationCandidate.promotion` é
*"Null if the candidate has not been promoted"*. Candidato é produzido; promover é ato separado.

RESSALVA REGISTRADA (regra 1): tudo isto vive em `client.beta.agents`, o namespace que o próprio
CLAUDE.md nomeia como o que mais se mexe. Nenhuma abstração por cima — se a forma mudar, muda este
arquivo e mais nada.

O QUE O JOB EXIGE, e por que a resposta pode ser "ainda não dá": `OptimizationJobInputs` pede o
agente com versão fixada, um `train_dataset` E `evaluators` — os três obrigatórios. Um tenant no
primeiro dia não tem dataset nem evaluator. A resposta honesta é dizer o que falta, não degradar
em silêncio para um "otimizador" nosso.
"""

from __future__ import annotations

import contextlib
from typing import Any

from app.modules.foundry.public import qualify_agent_name
from app.modules.tenancy.public import tenant_config


def _client():
    from azure.ai.projects import AIProjectClient
    from azure.identity import DefaultAzureCredential

    return AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
        allow_preview=True,
    )


def _campo(obj: Any, nome: str, default=None):
    """Lê de objeto OU de dict — a projeção do serviço varia entre as duas formas."""
    if isinstance(obj, dict):
        return obj.get(nome, default)
    return getattr(obj, nome, default)


def _candidato(c: Any) -> dict:
    """Um candidato, projetado para a tela.

    `promotion` sobe como booleano explícito: é o campo que separa proposta de publicação, e a
    interface precisa dele para nunca mostrar um candidato como se já estivesse no ar.
    """
    return {
        "id": _campo(c, "candidate_id"),
        "name": _campo(c, "name"),
        "mutations": _campo(c, "mutations") or {},
        "avg_score": _campo(c, "avg_score"),
        "avg_tokens": _campo(c, "avg_tokens"),
        "eval_run_id": _campo(c, "eval_run_id"),
        "promoted": _campo(c, "promotion") is not None,
    }


def list_optimizations(limit: int = 20) -> list[dict]:
    """Os jobs de otimização do projeto, projetados. LEITURA."""
    client = _client()
    try:
        saida = []
        for job in client.beta.agents.list_optimization_jobs():
            resultado = _campo(job, "result")
            saida.append(
                {
                    "id": _campo(job, "id"),
                    "status": _campo(job, "status"),
                    "created_at": _campo(job, "created_at"),
                    "best": _campo(resultado, "best") if resultado else None,
                    "candidates": len(_campo(resultado, "candidates") or []) if resultado else 0,
                    # Avisos não-fatais do serviço. Escondê-los faria um job "bem-sucedido" com
                    # ressalva parecer limpo.
                    "warnings": list(_campo(job, "warnings") or []),
                }
            )
            if len(saida) >= limit:
                break
        return saida
    finally:
        with contextlib.suppress(Exception):
            client.close()


def get_optimization(job_id: str) -> dict:
    """Um job com seus candidatos pontuados. LEITURA — não promove nada."""
    client = _client()
    try:
        job = client.beta.agents.get_optimization_job(job_id)
        resultado = _campo(job, "result")
        candidatos = [_candidato(c) for c in (_campo(resultado, "candidates") or [])] if resultado else []
        # Maior nota primeiro: a pergunta da tela é "qual ficou melhor", e ordenar por criação
        # obrigaria a pessoa a procurar. `None` vai para o fim em vez de quebrar a ordenação.
        candidatos.sort(key=lambda c: (c["avg_score"] is None, -(c["avg_score"] or 0)))
        return {
            "id": _campo(job, "id"),
            "status": _campo(job, "status"),
            "error": _campo(job, "error"),
            "warnings": list(_campo(job, "warnings") or []),
            "baseline": _campo(resultado, "baseline") if resultado else None,
            "best": _campo(resultado, "best") if resultado else None,
            "candidates": candidatos,
        }
    finally:
        with contextlib.suppress(Exception):
            client.close()


def start_optimization(
    agent: str, version: str, train_dataset: dict, evaluators: list[dict]
) -> dict:
    """Dispara o job. NÃO promove candidato — promover continua sendo ato humano separado.

    Os três insumos são exigidos pelo serviço, não por nós. Recusar aqui, nomeando o que falta, é
    melhor que mandar um payload incompleto e traduzir o 400 da plataforma depois.
    """
    if not agent:
        raise ValueError("Informe o agente a otimizar.")
    if not version:
        raise ValueError("Informe a versão do agente — a otimização parte de uma versão fixada.")
    if not train_dataset:
        raise ValueError(
            "A otimização exige um dataset de treino. Gere um com um job de geração de dados "
            "(DataGenerationJob) ou registre um dataset existente."
        )
    if not evaluators:
        raise ValueError(
            "A otimização exige ao menos um avaliador — é contra a nota dele que os candidatos "
            "são comparados. Sem isso não há 'melhor', só 'diferente'."
        )

    from azure.ai.projects.models import OptimizationJob, OptimizationJobInputs

    client = _client()
    try:
        job = client.beta.agents.begin_create_optimization_job(
            OptimizationJob(
                inputs=OptimizationJobInputs(
                    agent={"name": qualify_agent_name(agent), "version": str(version)},
                    train_dataset=train_dataset,
                    evaluators=evaluators,
                )
            )
        )
        # O poller devolve o job enfileirado; NÃO esperamos aqui. Otimização é longa, e segurar
        # um request HTTP até o fim dela transformaria a tela num timeout.
        atual = getattr(job, "_initial_response", None) or job
        return {
            "id": _campo(atual, "id"),
            "status": _campo(atual, "status") or "queued",
            "agent": qualify_agent_name(agent),
            "version": str(version),
        }
    finally:
        with contextlib.suppress(Exception):
            client.close()
