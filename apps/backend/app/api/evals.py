import contextlib
import json
from pathlib import Path

from fastapi import APIRouter

from app.core.auth import auth_dependencies

router = APIRouter()

# backend/app/api/evals.py -> backend/eval/runs.jsonl
_RUNS = Path(__file__).resolve().parents[2] / "eval" / "runs.jsonl"


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
