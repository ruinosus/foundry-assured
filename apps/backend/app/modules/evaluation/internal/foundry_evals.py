"""Read evaluation runs + scores live from Foundry (the canonical store).

The offline harness (eval/run_eval.py --cloud) creates eval runs in the Foundry
project via FoundryEvals; their scores live in the portal. This surfaces them in
the app's /evals page so it shows real groundedness/relevance/coherence results
instead of an empty local mirror.

The Foundry data plane is OpenAI-compatible for evals: project.get_openai_client()
exposes .evals.list() / .evals.runs.list(eval_id) / each run's result_counts +
per_testing_criteria_results + report_url. Verified against azure-ai-projects 2.2.0.
"""

from __future__ import annotations

import functools
import logging

from azure.ai.projects import AIProjectClient
from azure.identity import DefaultAzureCredential

from app.modules.tenancy.public import tenant_config

logger = logging.getLogger(__name__)


@functools.lru_cache(maxsize=1)
def _openai_client():
    # The app's own identity (not OBO): eval results are project-wide, not per-user.
    project = AIProjectClient(
        endpoint=tenant_config().foundry_project_endpoint,
        credential=DefaultAzureCredential(),
    )
    return project.get_openai_client()


def list_eval_runs(limit: int = 8) -> list[dict]:
    """Compatibilidade: só as execuções. Prefira `read_eval_runs`, que diz o que houve."""
    return read_eval_runs(limit)["runs"]


def read_eval_runs(limit: int = 8) -> dict:
    """As execuções recentes E o motivo, quando não há nenhuma.

    POR QUE ISTO MUDOU. A versão anterior devolvia `[]` para tudo: projeto sem execução, credencial
    sem permissão, serviço fora do ar. A tela então dizia "nenhuma execução encontrada, rode o
    eval" — conselho errado em dois dos três casos, e impossível de distinguir. É o mesmo defeito
    que as telas de agentes e conhecimento já haviam corrigido: **erro de leitura não é lista
    vazia**.

    Agora `reason` vem preenchido quando a lista está vazia por falha, e `null` quando está vazia
    porque realmente não há execução.
    """
    if not tenant_config().foundry_project_endpoint:
        return {"runs": [], "reason": "O endpoint do projeto do Foundry não está configurado."}
    try:
        oai = _openai_client()
        evals = sorted(
            oai.evals.list(), key=lambda e: e.created_at or 0, reverse=True
        )[:6]
        runs: list[dict] = []
        for ev in evals:
            for r in list(oai.evals.runs.list(ev.id))[:3]:
                rc = r.result_counts
                # Skip empty/no-score runs (e.g. continuous-eval probes with 0 items).
                if not getattr(rc, "total", 0) and not r.per_testing_criteria_results:
                    continue
                runs.append(
                    {
                        "id": r.id,
                        "eval_name": ev.name,
                        "status": r.status,
                        "created_at": r.created_at,
                        "report_url": r.report_url,
                        "total": getattr(rc, "total", 0),
                        "passed": getattr(rc, "passed", 0),
                        "failed": getattr(rc, "failed", 0),
                        "criteria": [
                            {
                                "name": c.testing_criteria,
                                "passed": c.passed,
                                "total": c.passed + c.failed + c.errored + c.skipped,
                            }
                            for c in (r.per_testing_criteria_results or [])
                        ],
                    }
                )
        runs.sort(key=lambda x: x["created_at"] or 0, reverse=True)
        # Lista vazia SEM falha é informação legítima: o projeto não tem execução ainda, e aí o
        # conselho de rodar o eval está certo. Só neste caso `reason` fica nulo.
        return {"runs": runs[:limit], "reason": None}
    except Exception as ex:  # noqa: BLE001 — leitura, nunca derruba a página
        logger.warning("Foundry eval listing failed: %s", ex)
        # A mensagem do serviço sobe: "sem permissão" e "não achei nada" pedem ações diferentes,
        # e esconder qual é os torna o mesmo problema insolúvel.
        return {"runs": [], "reason": f"Não foi possível ler as avaliações do Foundry: {ex}"}
