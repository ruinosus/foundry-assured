from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.core.auth import auth_dependencies
from app.core.settings import settings
from app.core.tenant import tenant_config
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


@router.post("/cockpit", dependencies=_hosted_deps("cockpit"))
async def cockpit(request: Request) -> StreamingResponse:
    """Grounded Cockpit expert with STRUCTURED citations — the Responses API run AS THE USER (OBO),
    grounded on docs from the `retrieve()` seam over the searchIndex-backed cockpit KB (cockpit-si-kb).
    Per-user document ACL rides the x-ms-query-source-authorization header inside retrieve(). One
    archetype (app/services/grounded.stream_grounded). See the 2026-07-01 spec.

    (Interim duck-typed domain — Task 6 replaces this endpoint with a mount loop.)"""
    from types import SimpleNamespace

    from app.agents.prompts import COCKPIT_INSTRUCTIONS
    from app.core.auth import current_user
    from app.services.grounded import stream_grounded

    cfg = tenant_config()
    domain = SimpleNamespace(
        kb_name=cfg.cockpit_searchindex_knowledge_base,  # cockpit-si-kb (native searchIndex retrieve)
        ks_name=cfg.cockpit_searchindex_knowledge_source,  # cockpit-docbundles-si-ks
        instructions=COCKPIT_INSTRUCTIONS,
        search_endpoint=cfg.azure_search_endpoint,
        search_index=cfg.cockpit_search_index,  # direct-search fallback target (ACL trims here too)
    )
    # Capture the user HERE (contextvar is set by the auth dep); it's lost inside the stream generator.
    return StreamingResponse(
        stream_grounded(await request.json(), domain, current_user()),
        media_type="text/event-stream",
    )


@router.post("/selfwiki", dependencies=_hosted_deps("selfwiki"))
async def selfwiki(request: Request) -> StreamingResponse:
    """Grounded Selfwiki expert with structured citations — same one-archetype path as /cockpit but
    single-audience (no ACL: selfwiki-kb has no permission metadata, so retrieve() omits the header).

    (Interim duck-typed domain — Task 6 replaces this endpoint with a mount loop.)"""
    from types import SimpleNamespace

    from app.agents.prompts import SELFWIKI_INSTRUCTIONS
    from app.core.auth import current_user
    from app.services.grounded import stream_grounded

    cfg = tenant_config()
    domain = SimpleNamespace(
        kb_name=cfg.selfwiki_search_knowledge_base,
        instructions=SELFWIKI_INSTRUCTIONS,
        search_endpoint=cfg.azure_search_endpoint,
        search_index=None,  # no direct-search fallback target; native KB retrieve only
    )
    return StreamingResponse(
        stream_grounded(await request.json(), domain, current_user()),
        media_type="text/event-stream",
    )


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


@router.post("/cockpit-hosted", dependencies=_hosted_deps("cockpit"))
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


@router.post("/selfwiki-hosted", dependencies=_hosted_deps("selfwiki"))
async def selfwiki_hosted(request: Request) -> StreamingResponse:
    """AG-UI twin of /selfwiki — the deployed selfwiki-expert hosted agent (Responses protocol),
    streamed as AG-UI. Keyless: the MI can invoke hosted agents where the live path 403s."""
    body = await request.json()
    return StreamingResponse(
        stream_agui(body, tenant_config().selfwiki_hosted_agent_name),
        media_type="text/event-stream",
    )


@router.post("/platform-hosted", dependencies=_hosted_deps("platform"))
async def platform_hosted(request: Request) -> StreamingResponse:
    """AG-UI twin of /platform — the deployed platform hosted agent over the Invocations
    protocol, streamed as AG-UI. Same Entra gate (+ shared-mode domain entitlement)."""
    body = await request.json()
    return StreamingResponse(stream_platform_agui(body), media_type="text/event-stream")
