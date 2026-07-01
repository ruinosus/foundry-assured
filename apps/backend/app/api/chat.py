from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.auth import auth_dependencies
from app.core.tenant import tenant_config
from app.domains import _domain_deps
from app.services.hosted import stream_agui, stream_platform_agui

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
    return StreamingResponse(
        stream_agui(body, tenant_config().hosted_agent_name), media_type="text/event-stream"
    )


@router.post("/cockpit-hosted", dependencies=_domain_deps("cockpit"))
async def cockpit_hosted(request: Request) -> StreamingResponse:
    """AG-UI twin of /cockpit — the deployed cockpit-expert hosted agent (Responses protocol),
    streamed as AG-UI. The managed identity is authorized to invoke hosted agents (unlike raw
    inference), so this is the keyless path that actually answers. Same Entra gate (+ shared-mode
    domain entitlement)."""
    body = await request.json()
    return StreamingResponse(
        stream_agui(body, tenant_config().cockpit_hosted_agent_name),
        media_type="text/event-stream",
    )


@router.post("/selfwiki-hosted", dependencies=_domain_deps("selfwiki"))
async def selfwiki_hosted(request: Request) -> StreamingResponse:
    """AG-UI twin of /selfwiki — the deployed selfwiki-expert hosted agent (Responses protocol),
    streamed as AG-UI. Keyless: the MI can invoke hosted agents where the live path 403s."""
    body = await request.json()
    return StreamingResponse(
        stream_agui(body, tenant_config().selfwiki_hosted_agent_name),
        media_type="text/event-stream",
    )


@router.post("/platform-hosted", dependencies=_domain_deps("platform"))
async def platform_hosted(request: Request) -> StreamingResponse:
    """AG-UI twin of /platform — the deployed platform hosted agent over the Invocations
    protocol, streamed as AG-UI. Same Entra gate (+ shared-mode domain entitlement)."""
    body = await request.json()
    return StreamingResponse(stream_platform_agui(body), media_type="text/event-stream")
