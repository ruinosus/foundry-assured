from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.auth import auth_dependencies
from app.services.hosted import stream_agui

router = APIRouter()


@router.post("/helpdesk-hosted", dependencies=auth_dependencies())
async def helpdesk_hosted(request: Request) -> StreamingResponse:
    """AG-UI endpoint that proxies the hosted agent, streaming Responses → AG-UI.

    Behind the same Entra bearer gate as the live `/helpdesk` endpoint
    (auth_dependencies → require_user when auth is enabled; a no-op in local dev).
    Without it the "Hosted agent" toggle would reach the agent unauthenticated.

    The live `/helpdesk` AG-UI workflow endpoint is registered on the app directly
    (app/main.py) via add_agent_framework_fastapi_endpoint — it isn't a router.
    """
    body = await request.json()
    return StreamingResponse(stream_agui(body), media_type="text/event-stream")
