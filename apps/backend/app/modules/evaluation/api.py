import contextlib
import json
from pathlib import Path

from fastapi import APIRouter

from app.shared.auth import auth_dependencies
from app.modules.evaluation.public import list_eval_runs

router = APIRouter()

# apps/backend/eval/runs.jsonl, anchored on the `app` package rather than counted from this
# file — the parents[2] this used to carry became app/modules/eval/ when ADR-017 moved it.
import app as _app

_RUNS = Path(_app.__file__).resolve().parent.parent / "eval" / "runs.jsonl"


@router.get("/eval/runs", dependencies=auth_dependencies())
def eval_runs(limit: int = 50) -> dict[str, list[dict]]:
    """Eval runs recorded by the offline harness (eval/run_eval.py), newest first.

    Behind the Entra bearer gate (no-op in local dev). The canonical store is the
    Foundry portal Evaluations tab; this local mirror is empty on a fresh deploy
    (evals run offline / in CI), so the frontend deep-links to the portal.
    """
    if not _RUNS.exists():
        return {"runs": []}
    runs: list[dict] = []
    for line in _RUNS.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            with contextlib.suppress(json.JSONDecodeError):
                runs.append(json.loads(line))
    runs.reverse()
    return {"runs": runs[:limit]}


@router.get("/eval/foundry", dependencies=auth_dependencies())
def foundry_eval_runs(limit: int = 8) -> dict[str, list[dict]]:
    """Live evaluation runs + scores read from the Foundry project (the canonical
    store) — groundedness/relevance/coherence pass counts per run, each linking to
    its portal report. This is what the /evals page renders.
    """
    return {"runs": list_eval_runs(limit)}
