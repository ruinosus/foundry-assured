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

from app.core.tenant import tenant_config

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
    """Recent Foundry eval runs (newest first) with per-criterion pass counts.

    Returns [] when Foundry isn't configured or unreachable — the page degrades to
    a "view in portal" prompt rather than erroring.
    """
    if not tenant_config().foundry_project_endpoint:
        return []
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
        return runs[:limit]
    except Exception as ex:  # noqa: BLE001 — read-only view, never 500 the page
        logger.warning("Foundry eval listing failed: %s", ex)
        return []
