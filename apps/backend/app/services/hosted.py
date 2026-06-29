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

from app.core.tenant import tenant_config

# Cached async OpenAI client (+ its project/credential) bound to the hosted agent.
_state: dict = {"client": None, "project": None, "credential": None}


async def _client():
    if _state["client"] is None:
        from azure.ai.projects.aio import AIProjectClient
        from azure.identity.aio import DefaultAzureCredential

        credential = DefaultAzureCredential()
        project = AIProjectClient(
            endpoint=tenant_config().foundry_project_endpoint,
            credential=credential,
            allow_preview=True,
        )
        client = project.get_openai_client(agent_name=tenant_config().hosted_agent_name)
        _state.update(
            client=await client if inspect.isawaitable(client) else client,
            project=project,
            credential=credential,
        )
    return _state["client"]


async def aclose() -> None:
    """Close the cached client + project + credential (called on app shutdown)."""
    import contextlib

    for obj in (_state["client"], _state["project"], _state["credential"]):
        if obj is not None:
            with contextlib.suppress(Exception):
                await obj.close()


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


async def stream_agui(body: dict) -> AsyncGenerator[str]:
    """Stream the hosted agent's Responses output as AG-UI SSE events."""
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
    try:
        client = await _client()
        events = await client.responses.create(input=user_text, stream=True)
        async for event in events:
            if getattr(event, "type", "") == "response.output_text.delta":
                delta = getattr(event, "delta", "") or ""
                if delta:
                    yield enc.encode(TextMessageContentEvent(message_id=message_id, delta=delta))
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        yield enc.encode(RunFinishedEvent(thread_id=thread_id, run_id=run_id))
    except Exception as exc:  # surface to the UI as a clean run error
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        yield enc.encode(RunErrorEvent(message=str(exc), code=type(exc).__name__))
