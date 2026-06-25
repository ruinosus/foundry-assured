from fastapi import APIRouter

from app.tools.tickets import list_tickets

router = APIRouter()


@router.get("/tickets")
def tickets(limit: int = 50) -> dict[str, list[dict]]:
    """Real tickets opened by the HITL approval flow (create_ticket tool)."""
    return {"tickets": list_tickets(limit)}
