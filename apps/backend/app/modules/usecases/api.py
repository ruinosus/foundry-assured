"""HTTP dos casos de uso — a camada que o negócio abre.

Leitura exige autenticação. Escrita (renomear, gravar fluxo) exige **Admin**: mudar o fluxo de um
caso muda o que o assistente faz para todo mundo.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.modules.usecases.public import (
    get_use_case,
    list_use_cases,
    outcomes,
    parse_assumption,
    rename_use_case,
    write_flow,
)
from app.shared.auth import auth_dependencies, require_role

router = APIRouter(prefix="/usecases", tags=["usecases"], dependencies=auth_dependencies())

_admin = [Depends(require_role("Admin"))]


def _guard(fn):
    """Erro de validação vira 400; falha de serviço vira 502. Um YAML inválido é problema de
    quem editou, e mandá-lo procurar no Azure seria mandar para o lugar errado."""
    try:
        return fn()
    except HTTPException:
        raise
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Casos de uso: {exc}") from exc


@router.get("")
def use_cases() -> dict:
    """Todos os casos, com as peças e os passos de cada um."""
    return {"use_cases": _guard(list_use_cases)}


@router.get("/{case_id}")
def use_case(case_id: str) -> dict:
    """Um caso com o YAML do fluxo — a tela de leitura e o canvas consomem o mesmo objeto."""
    return _guard(lambda: get_use_case(case_id))


@router.put("/{case_id}", dependencies=_admin)
def rename(case_id: str, body: dict) -> dict:
    """Renomeia o caso. O rótulo vai para o `metadata` dos agentes — quem abrir o portal do
    Foundry vê o mesmo nome que a tela mostra."""
    nome = str(body.get("name") or "").strip()
    if not nome:
        raise HTTPException(status_code=400, detail="Informe um nome.")
    return _guard(
        lambda: rename_use_case(case_id, nome, str(body.get("description") or ""))
    )


@router.put("/{case_id}/flow", dependencies=_admin)
async def save_flow(case_id: str, request: Request) -> dict:
    """Grava o fluxo, validando pelo próprio `WorkflowFactory` antes de escrever.

    O corpo é o YAML cru (text/plain ou JSON com `yaml`) — não um objeto nosso. O canvas
    serializa para a linguagem da Microsoft, e é isso que se grava: inventar um envelope aqui
    criaria um formato intermediário que ninguém mais lê.
    """
    tipo = request.headers.get("content-type") or ""
    if "application/json" in tipo:
        corpo = await request.json()
        yaml_text = str((corpo or {}).get("yaml") or "")
    else:
        yaml_text = (await request.body()).decode("utf-8", errors="replace")
    if not yaml_text.strip():
        raise HTTPException(status_code=400, detail="O fluxo está vazio.")
    return _guard(lambda: write_flow(case_id, yaml_text))


@router.post("/{case_id}/outcomes")
def case_outcomes(case_id: str, body: dict | None = None) -> dict:
    """O que este caso produziu, e o retorno sob a premissa informada.

    É POST e não GET porque a premissa vai no corpo — e ela é o parâmetro que muda o número. Um
    GET com os valores na querystring os colocaria no log de acesso e no histórico do browser,
    e "custo da hora da equipe" é dado que a empresa não escolheu publicar.

    A resposta traz o que é CONTADO e o que é ESTIMADO em campos separados. Sem essa separação, um
    número calculado sobre uma premissa se parece com uma medida — que é exatamente como um painel
    de ROI vira propaganda.
    """
    premissa = parse_assumption(body or {}) if body else None
    caso = _guard(lambda: get_use_case(case_id))
    return _guard(lambda: outcomes(caso, premissa))
