from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.auth import auth_dependencies
from app.core.settings import settings
from app.services.hosted import stream_agui, stream_platform_agui

router = APIRouter()


def _hosted_deps(domain_id: str) -> list:
    # mirrors main.py::_domain_deps (the canonical domain-gate helper) — keep the shared-gate logic in sync
    deps = auth_dependencies()
    if settings.deployment_mode == "shared":
        from fastapi import Depends
        from app.core.tenant import require_domain
        deps = [*deps, Depends(require_domain(domain_id))]
    return deps


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


@router.post("/platform-hosted", dependencies=_hosted_deps("platform"))
async def platform_hosted(request: Request) -> StreamingResponse:
    """AG-UI twin of /platform — the deployed platform hosted agent over the Invocations
    protocol, streamed as AG-UI. Same Entra gate (+ shared-mode domain entitlement)."""
    body = await request.json()
    return StreamingResponse(stream_platform_agui(body), media_type="text/event-stream")
