from fastapi import APIRouter, Depends

from app.modules.tickets.public import list_tickets
from app.shared.auth import auth_dependencies, require_role

router = APIRouter()


@router.get(
    "/tickets",
    dependencies=[*auth_dependencies(), Depends(require_role("Approver", "Admin"))],
)
def tickets(limit: int = 50) -> dict[str, list[dict]]:
    """Os chamados abertos pelo fluxo de aprovação (a tool `create_ticket`).

    EXIGE **Approver** ou **Admin**, e antes exigia só o bearer — qualquer pessoa autenticada lia
    os chamados de todo mundo. Um chamado carrega o problema de alguém descrito em texto livre;
    a lista inteira é um retrato do que está quebrado na empresa e de quem pediu o quê.

    O papel escolhido não é `Admin` sozinho de propósito: quem APROVA a escalação precisa poder
    ver o que já foi escalado, ou aprova sem contexto — e negar isso ao aprovador o empurraria a
    pedir a lista por fora, que é pior que dar acesso pelo caminho auditado.

    Gravado em `data/tickets.jsonl`, que é o mount do Azure Files no app deployado — o caminho é
    comparado com o bicep por `tests/tickets/store_path_test.py`, porque já errou duas vezes.
    """
    return {"tickets": list_tickets(limit)}
