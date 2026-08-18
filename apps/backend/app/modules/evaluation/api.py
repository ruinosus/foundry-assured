import contextlib
import json
from pathlib import Path

from fastapi import APIRouter

from app.modules.evaluation.public import read_eval_runs
from app.shared.auth import auth_dependencies

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
def foundry_eval_runs(limit: int = 8) -> dict:
    """As execuções de avaliação do projeto do Foundry — e o MOTIVO, quando não há nenhuma.

    A anotação é `dict`, não `dict[str, list[dict]]`, e isso não é preguiça: a resposta passou a
    ter `reason` (string ou null) ao lado de `runs` (lista). Com a anotação antiga o FastAPI
    validava a saída, encontrava uma string onde exigia lista, e devolvia 500 — a tela trocava
    "nenhuma execução" por "erro 500", que é pior: some a informação e some o dado.

    Foi regressão minha ao tornar a falha visível. O tipo faz parte do contrato; mudá-lo pela
    metade é mudar o contrato pela metade.
    """
    return read_eval_runs(limit)
