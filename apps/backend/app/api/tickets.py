from fastapi import APIRouter

from app.core.auth import auth_dependencies
from app.tools.tickets import list_tickets

router = APIRouter()


@router.get("/tickets", dependencies=auth_dependencies())
def tickets(limit: int = 50) -> dict[str, list[dict]]:
    """Real tickets opened by the HITL approval flow (create_ticket tool).

    Behind the Entra bearer gate (no-op in local dev). Persisted to data/tickets.jsonl,
    which is an Azure Files mount in the deployed app so tickets survive scale-to-zero.
    """
    return {"tickets": list_tickets(limit)}
