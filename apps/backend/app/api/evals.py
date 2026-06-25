import contextlib
import json
from pathlib import Path

from fastapi import APIRouter

router = APIRouter()

# backend/app/api/evals.py -> backend/eval/runs.jsonl
_RUNS = Path(__file__).resolve().parents[2] / "eval" / "runs.jsonl"


@router.get("/eval/runs")
def eval_runs(limit: int = 50) -> dict[str, list[dict]]:
    """Eval runs recorded by the offline harness (eval/run_eval.py), newest first.

    Read-only showcase data — no auth — consumed by the frontend /evals page,
    which links each run to its Foundry portal report (report_url).
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
