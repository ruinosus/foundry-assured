from fastapi import APIRouter, Request
from fastapi.responses import StreamingResponse

from app.modules.hosted.public import stream_agui, stream_platform_agui
from app.modules.tenancy.public import domain_deps, tenant_config
from app.shared.auth import auth_dependencies

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


@router.post("/platform-hosted", dependencies=domain_deps("platform"))
async def platform_hosted(request: Request) -> StreamingResponse:
    """AG-UI twin of /platform — the deployed platform hosted agent over the Invocations
    protocol, streamed as AG-UI. Same Entra gate (+ shared-mode domain entitlement)."""
    body = await request.json()
    return StreamingResponse(stream_platform_agui(body), media_type="text/event-stream")


@router.post("/foundry-agent/{name}", dependencies=auth_dependencies())
async def foundry_agent(name: str, request: Request) -> StreamingResponse:
    """Conversa com QUALQUER agente do Foundry, pelo nome.

    ISTO FECHA UM CICLO QUE ESTAVA ABERTO, e a falta era estrutural: o produto tinha um caminho
    para CRIAR agente (o wizard, que publica no Foundry) e nenhum para USAR o que foi criado. E
    tinha um caminho para usar agente (os domínios do registry) que não passa pelo Foundry. Quem
    criasse um agente pela tela o veria na lista e não teria o que fazer com ele.

    As duas rotas acima já faziam exatamente isto — `stream_agui(body, agent_name)` sempre recebeu
    o nome como parâmetro. Só estavam presas a dois nomes de configuração. Generalizar foi remover
    a amarra, não escrever runtime novo.

    O NOME VEM DO CAMINHO, e por isso passa por `qualify`: valida o formato antes de virar chamada
    e, no modo shared, prefixa por tenant — sem isso um tenant conversaria com o agente de outro
    escrevendo o nome certo na URL.
    """
    from app.modules.foundry.public import qualify_agent_name

    body = await request.json()
    return StreamingResponse(
        stream_agui(body, qualify_agent_name(name)), media_type="text/event-stream"
    )
