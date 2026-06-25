from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.services.hosted import stream_agui

router = APIRouter()


@router.post("/helpdesk-hosted")
async def helpdesk_hosted(request: Request) -> StreamingResponse:
    """AG-UI endpoint that proxies the hosted agent, streaming Responses → AG-UI.

    The live `/helpdesk` AG-UI workflow endpoint is registered on the app directly
    (app/main.py) via add_agent_framework_fastapi_endpoint — it isn't a router.
    """
    body = await request.json()
    return StreamingResponse(stream_agui(body), media_type="text/event-stream")
