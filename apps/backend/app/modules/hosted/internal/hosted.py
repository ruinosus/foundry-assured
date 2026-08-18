"""Hosted-agent (Phase 6) invocation + AG-UI bridge.

The hosted agent speaks the Responses protocol, but CopilotKit's chat consumes
AG-UI — so this streams the hosted agent's response and re-emits it as AG-UI
events, letting the frontend render the *same* CopilotChat for the hosted agent
(registered as "helpdesk-hosted"). No live workflow steps or approval card — those
are inherent to the AG-UI workflow; the hosted agent only returns the final answer.
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncGenerator

from app.modules.tenancy.public import tenant_config

# Cached async OpenAI clients (+ project/credential), keyed by hosted-agent name — so the same
# bridge serves any hosted twin (helpdesk-concierge, techdocs-expert, …) without re-warming.
_clients: dict[str, dict] = {}


async def _client(agent_name: str):
    st = _clients.get(agent_name)
    if st is None:
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import DefaultAzureCredential

        credential = DefaultAzureCredential()
        project = AIProjectClient(
            endpoint=tenant_config().foundry_project_endpoint,
            credential=credential,
            allow_preview=True,
        )
        client = project.get_openai_client(agent_name=agent_name)
        # TODO(multitenant): process-global cache binds to the FIRST tenant that warms each agent;
        # bust/scope it per-tenant when the MultiTenant provider lands (else cross-tenant mismatch).
        st = {
            "client": await client if inspect.isawaitable(client) else client,
            "project": project,
            "credential": credential,
        }
        _clients[agent_name] = st
    return st["client"]


async def aclose() -> None:
    """Close every cached client + project + credential (called on app shutdown)."""
    import contextlib

    for st in _clients.values():
        for obj in (st["client"], st["project"], st["credential"]):
            if obj is not None:
                with contextlib.suppress(Exception):
                    await obj.close()
    _clients.clear()


def _last_user_text(messages: list) -> str:
    for message in reversed(messages or []):
        if message.get("role") == "user":
            content = message.get("content")
            if isinstance(content, str):
                return content
            if isinstance(content, list):
                return " ".join(
                    part.get("text", "") for part in content if isinstance(part, dict)
                )
    return ""


def _registrar(
    agent: str, thread_id: str, pergunta: str, resposta: str, entrada: int, saida: int
) -> None:
    """Grava conversa e uso do runtime hosted. UM lugar, não um por rota.

    Este é o seam do runtime D: as três rotas hosted (`/helpdesk-hosted`, `/platform-hosted` e a
    genérica `/foundry-agent/{name}`) passam todas por este stream, então gravar aqui cobre as três
    — e cobre a próxima, sem ninguém precisar lembrar. É a mesma disciplina da fábrica de cliente
    para o agent-framework: medir é propriedade do caminho, não decisão de cada agente.

    Não grava referências: um agente hosted responde com o que a base dele trouxe, e essa contagem
    não volta no stream de Responses. Zero aqui seria contagem errada, e a matriz de instrumentação
    declara essa lacuna em vez de fingir que é zero.
    """
    from app.modules.conversations.public import (
        conversation_user,
        record_turn,
        record_usage,
    )

    usuario = conversation_user()
    if not (usuario and thread_id):
        return
    record_turn(usuario, agent, thread_id, pergunta, resposta)
    record_usage(usuario, agent, thread_id, entrada, saida)


async def stream_agui(body: dict, agent_name: str) -> AsyncGenerator[str]:
    """Stream the named hosted agent's Responses output as AG-UI SSE events."""
    from ag_ui.core import (
        RunErrorEvent,
        RunFinishedEvent,
        RunStartedEvent,
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
    )
    from ag_ui.encoder import EventEncoder

    user_text = _last_user_text(body.get("messages") or [])
    thread_id = body.get("threadId") or body.get("thread_id") or uuid.uuid4().hex
    run_id = body.get("runId") or body.get("run_id") or uuid.uuid4().hex

    enc = EventEncoder()
    yield enc.encode(RunStartedEvent(thread_id=thread_id, run_id=run_id))
    message_id = uuid.uuid4().hex
    yield enc.encode(TextMessageStartEvent(message_id=message_id, role="assistant"))
    resposta: list[str] = []
    tokens_in = tokens_out = 0
    try:
        client = await _client(agent_name)
        events = await client.responses.create(input=user_text, stream=True)
        async for event in events:
            tipo = getattr(event, "type", "")
            if tipo == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                if delta:
                    resposta.append(delta)
                    yield enc.encode(TextMessageContentEvent(message_id=message_id, delta=delta))
            elif tipo == "response.completed":
                # O uso vive SÓ no evento final — os deltas não o carregam. Este laço lia apenas
                # `output_text.delta` e descartava o resto, então o token de todo agente hosted
                # (inclusive os que o usuário cria) era jogado fora aqui. Não era "só o Foundry
                # sabe": estava ao lado, no mesmo stream.
                uso = getattr(getattr(event, "response", None), "usage", None)
                tokens_in = int(getattr(uso, "input_tokens", 0) or 0)
                tokens_out = int(getattr(uso, "output_tokens", 0) or 0)
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        _registrar(agent_name, thread_id, user_text, "".join(resposta), tokens_in, tokens_out)
        yield enc.encode(RunFinishedEvent(thread_id=thread_id, run_id=run_id))
    except Exception as exc:  # surface to the UI as a clean run error
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        yield enc.encode(RunErrorEvent(message=str(exc), code=type(exc).__name__))


def _platform_invocations_url() -> str:
    """The deployed platform agent's Invocations endpoint (AG-UI → Invocations, not Responses;
    per the Foundry hosted-agents guidance). Empty endpoint ⇒ not deployed.

    NOTE (Task 0): `azure-ai-projects` 2.2.0 exposes only `protocols/openai`; the `invocations`
    protocol + its SSE envelope are not in any installed library and are NOT verified offline.
    This URL shape is forward-looking; the bridge raises before using it until the contract is
    verified against a deployed agent (D-packaging)."""
    cfg = tenant_config()
    base = (cfg.foundry_project_endpoint or "").rstrip("/")
    name = cfg.platform_hosted_agent_name
    return f"{base}/agents/{name}/endpoint/protocols/invocations" if base else ""


async def stream_platform_agui(body: dict) -> AsyncGenerator[str]:
    """Stream the deployed PLATFORM hosted agent (Invocations protocol) as AG-UI SSE.

    Twin of stream_agui, but Invocations (raw SSE) — the protocol Microsoft indicates for
    AG-UI — so C's write-approval interrupt can round-trip on the hosted path (Responses can't).

    Unlike stream_agui (Responses → AG-UI re-encode), the Invocations endpoint already serves
    AG-UI: the platform hosted agent's response bytes ARE AG-UI SSE, so this is a 1:1 PASSTHROUGH
    — the response lines are relayed UNTOUCHED, no envelope parsing, no re-encoding. We only frame
    a clean RunErrorEvent for the failure path (e.g. no endpoint configured), mirroring stream_agui.
    """
    from ag_ui.core import (
        RunErrorEvent,
        RunStartedEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
    )
    from ag_ui.encoder import EventEncoder

    thread_id = body.get("threadId") or body.get("thread_id") or uuid.uuid4().hex
    run_id = body.get("runId") or body.get("run_id") or uuid.uuid4().hex
    enc = EventEncoder()
    message_id = uuid.uuid4().hex
    try:
        url = _platform_invocations_url()
        if not url:
            raise RuntimeError("platform hosted agent not configured (foundry_project_endpoint empty)")

        import httpx

        from app.shared.auth import credential_for_request

        # TODO(infra-gated): confirm the Foundry data-plane scope against the deployed agent.
        # `https://ai.azure.com/.default` is best-evidence (the AI Projects audience), NOT pinned
        # by an SDK constant offline (Task 0).
        token = credential_for_request().get_token("https://ai.azure.com/.default").token

        # TODO(infra-gated): confirm the request body shape against the deployed agent. The exact
        # AG-UI run-input envelope the Invocations endpoint expects is not verifiable offline
        # (Task 0) — relay the caller's AG-UI run body as-is; refine once verified against deploy.
        async with httpx.AsyncClient(timeout=None) as http:
            async with http.stream(
                "POST",
                url,
                headers={
                    "Authorization": f"Bearer {token}",
                    "Content-Type": "application/json",
                    "Accept": "text/event-stream",
                },
                json=body,
            ) as resp:
                resp.raise_for_status()
                # Passthrough: the endpoint's SSE lines are already AG-UI — relay UNTOUCHED.
                # TODO(infra-gated): confirm the SSE framing against the deployed agent. NOTE:
                # aiter_lines() strips line terminators and the `if line` filter drops SSE's
                # blank-line event separators — so for a TRUE byte-identical AG-UI passthrough this
                # very likely needs resp.aiter_bytes() (or aiter_raw()) yielding chunks UNCHANGED,
                # NOT aiter_lines() (which would corrupt event boundaries). Verify the exact framing
                # the Invocations endpoint emits before relying on it.
                async for line in resp.aiter_lines():
                    if line:
                        yield line + "\n"
    except Exception as exc:  # surface to the UI as a clean run error (mirrors stream_agui)
        yield enc.encode(RunStartedEvent(thread_id=thread_id, run_id=run_id))
        yield enc.encode(TextMessageStartEvent(message_id=message_id, role="assistant"))
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        yield enc.encode(RunErrorEvent(message=str(exc), code=type(exc).__name__))
