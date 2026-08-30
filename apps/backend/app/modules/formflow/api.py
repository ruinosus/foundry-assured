"""HTTP dos formulários declarados.

LEITURA AUTENTICADA, SEM PAPEL. O manifesto descreve a FORMA do formulário — que campos existem,
que regras valem, o que a revisão diz. Ele não carrega dado de ninguém, e é a mesma forma para
todo mundo. Exigir Admin para lê-lo faria a tela de criação não renderizar para quem tem
permissão de criar mas não de administrar — e a autorização que importa está onde sempre esteve:
no endpoint que PUBLICA o recurso, que exige o papel declarado no próprio `plan`.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.modules.formflow.public import (
    FlowInvalid,
    FlowNotFound,
    list_copilots,
    list_flows,
    load_copilot,
    load_flow,
    verificar_alvos,
)
from app.shared.auth import auth_dependencies

router = APIRouter(prefix="/flows", tags=["formflow"], dependencies=auth_dependencies())


@router.get("")
def flows() -> dict:
    """Os formulários publicados."""
    return {"flows": list_flows()}


@router.get("/{name}")
def flow(name: str) -> dict:
    """Um manifesto, como a tela o consome.

    404 e 422 SÃO DIFERENTES, e a tela precisa dos dois: "não existe formulário com esse nome" é
    outra coisa que "o formulário existe e está torto". Achatar os dois num 500 faria um erro de
    edição do manifesto parecer indisponibilidade do backend, e alguém tentaria de novo em vez de
    corrigir o documento.
    """
    try:
        return load_flow(name)
    except FlowNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FlowInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# ── Copilotos ────────────────────────────────────────────────────────────────────────────────
#
# Mesmo router, porque é a mesma classe de recurso: documento declarativo que a tela consome. Um
# router separado significaria um prefixo separado, e `/copilots` vs `/flows` são dois nomes para
# "o que este produto declara".

copilots = APIRouter(prefix="/copilots", tags=["formflow"], dependencies=auth_dependencies())


@copilots.get("")
def listar_copilotos() -> dict:
    """Os copilotos publicados. `hitl` é política, não copiloto — sai da lista."""
    return {"copilots": [c for c in list_copilots() if c != "hitl"]}


@copilots.get("/{name}")
def copiloto(name: str) -> dict:
    """Um copiloto, com os problemas dos alvos JUNTO.

    Os problemas viajam com o documento em vez de virarem um 422: um copiloto com alvo torto
    ainda é legível — quem está editando quer ver o documento E o que está errado nele, não uma
    tela vazia com uma mensagem de erro. Quem decide o que fazer com `target_problems` é a tela.
    """
    try:
        doc = load_copilot(name)
    except FlowNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except FlowInvalid as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {**doc, "target_problems": verificar_alvos(doc)}
