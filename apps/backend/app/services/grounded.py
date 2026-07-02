"""Grounded structured-citations bridge — ONE archetype over the `retrieve()` seam.

Four stations, one path (the old acl/MCP fork is gone — retrieval lives behind `app.services.retrieval`):

1. **Identity (OBO):** the SYNTHESIS (Responses API) runs AS THE SIGNED-IN USER (OBO for
   `https://ai.azure.com/.default` → no 403 on inference). The `user` MUST be captured in the endpoint
   and passed in — the `current_user()` contextvar is LOST inside this StreamingResponse async generator
   (verified), so we never read it here (`_async_credential`).
2. **Retrieve:** ONE call — `docs = await retrieve(user_text, user, domain)`. The seam does native
   searchIndex retrieve (per-user ACL via the `x-ms-query-source-authorization` header) or the
   direct-search fallback, plus dedupe + reindex. Returns `[{index, source, url, snippet}]`.
3. **Synthesize:** ALWAYS `build_synthesis_kwargs(...)` — the retrieved docs are the ONLY grounding
   context (RULE #4: ≥1 citation; the model answers only from these, cites by [n], else "não sei").
4. **Emit:** re-emit AG-UI SSE (text deltas + a `sources` CUSTOM event with `content` capped at 800 chars
   so the UI can render the source inline — the blob URLs are private and 403 on open).

Verified live in the STEP 0 / STEP 0.5 findings (docs/superpowers/plans/).
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncGenerator

from app.core.settings import settings
from app.core.tenant import tenant_config

# Prepended to the synthesis input — the model answers ONLY from the retrieved documents and cites them
# by their [n] number.
SYNTHESIS_DIRECTIVE = (
    "Responda APENAS com base nos DOCUMENTOS fornecidos abaixo — nunca use conhecimento próprio. "
    "Cite a fonte de cada afirmação pelo seu número entre colchetes, ex.: [1]. Se os documentos não "
    "contiverem a resposta, diga que não sabe."
)


def build_synthesis_kwargs(user_text: str, domain, docs: list[dict], *, model: str) -> dict:
    """The synthesis `responses.create(**kwargs)` payload. Pure — no I/O.

    `docs` is the list of retrieved (already ACL-trimmed + deduped) documents, each
    `{index, source, url, snippet}`. The snippets become the model's ONLY grounding context.
    `domain` is duck-typed: reads `.instructions`."""
    context = "\n\n".join(f"[{d['index']}] {d['source']}:\n{d.get('snippet', '')}" for d in docs)
    body = (
        f"{SYNTHESIS_DIRECTIVE}\n\n=== DOCUMENTOS ===\n{context}\n\n=== PERGUNTA ===\n{user_text}"
        if docs
        else f"{SYNTHESIS_DIRECTIVE}\n\n(Nenhum documento autorizado foi encontrado.)\n\n=== PERGUNTA ===\n{user_text}"
    )
    return {
        "model": model,
        "input": body,
        "instructions": getattr(domain, "instructions", "") or "",
        "stream": True,
    }


def _async_credential(user):
    """Async credential AS THE SIGNED-IN USER (OBO), mirroring app.core.auth.credential_for_request.
    The `user` MUST be captured in the endpoint and passed in — the `current_user()` contextvar is
    LOST inside this StreamingResponse async generator (verified), so reading it here would return
    None and silently fall back to the app MI, which 403s on raw inference (the service-principal gap).
    Falls back to DefaultAzureCredential (aio) when auth is off (local dev) or no user."""
    from azure.identity.aio import DefaultAzureCredential, OnBehalfOfCredential

    if settings.auth_enabled and user is not None:
        return OnBehalfOfCredential(
            tenant_id=settings.entra_tenant_id,
            client_id=settings.entra_api_client_id,
            client_secret=settings.entra_api_client_secret,
            user_assertion=user.access_token,
        )
    return DefaultAzureCredential()


async def stream_grounded(body: dict, domain, user=None) -> AsyncGenerator[str]:
    """Stream a grounded answer (as the user) as AG-UI SSE: text deltas + a `sources` CUSTOM event.

    ONE archetype: retrieve via the `retrieve()` seam (per-user ACL / dedupe live there), then
    synthesize from ONLY those docs and emit their sources as citations.

    `user` is the signed-in User, CAPTURED IN THE ENDPOINT and passed in (the current_user() contextvar
    doesn't survive into this generator — see _async_credential). None → app identity (dev/no-auth)."""
    from ag_ui.core import (
        CustomEvent,
        RunErrorEvent,
        RunFinishedEvent,
        RunStartedEvent,
        TextMessageContentEvent,
        TextMessageEndEvent,
        TextMessageStartEvent,
    )
    from ag_ui.encoder import EventEncoder
    from azure.ai.projects.aio import AIProjectClient

    from app.services.hosted import _last_user_text
    from app.services.retrieval import retrieve

    user_text = _last_user_text(body.get("messages") or [])
    thread_id = body.get("threadId") or body.get("thread_id") or uuid.uuid4().hex
    run_id = body.get("runId") or body.get("run_id") or uuid.uuid4().hex

    enc = EventEncoder()
    yield enc.encode(RunStartedEvent(thread_id=thread_id, run_id=run_id))
    message_id = uuid.uuid4().hex
    yield enc.encode(TextMessageStartEvent(message_id=message_id, role="assistant"))

    cfg = tenant_config()
    credential = _async_credential(user)  # station 1: OBO — the synthesis runs AS THE USER
    proj = AIProjectClient(
        endpoint=cfg.foundry_project_endpoint, credential=credential, allow_preview=True
    )
    try:
        # Station 2 — retrieve: ONE line. The seam owns identity/ACL/dedupe (app.services.retrieval).
        docs = await retrieve(user_text, user, domain)

        client = proj.get_openai_client()
        client = await client if inspect.isawaitable(client) else client

        # Station 3 — synthesize: the retrieved docs are the ONLY grounding context (RULE #4).
        kwargs = build_synthesis_kwargs(user_text, domain, docs, model=cfg.foundry_model)

        # Station 4 — emit: include the retrieved snippet as `content` so the UI can show the source
        # INLINE on click (the blob URLs are private — allowBlobPublicAccess=false — so opening 403s).
        # 800-char cap preserved; dedupe already done in retrieve().
        sources = [
            {"index": d["index"], "source": d["source"], "url": d["url"],
             "content": (d.get("snippet") or "")[:800]}
            for d in docs
        ]

        stream = await client.responses.create(**kwargs)
        async for ev in stream:
            if getattr(ev, "type", "") == "response.output_text.delta":
                delta = getattr(ev, "delta", "") or ""
                if delta:
                    yield enc.encode(TextMessageContentEvent(message_id=message_id, delta=delta))
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        if sources:
            yield enc.encode(CustomEvent(name="sources", value=sources))
        yield enc.encode(RunFinishedEvent(thread_id=thread_id, run_id=run_id))
    except Exception as exc:  # surface to the UI as a clean run error (mirrors hosted.stream_agui)
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        yield enc.encode(RunErrorEvent(message=str(exc), code=type(exc).__name__))
    finally:
        import contextlib

        for obj in (proj, credential):
            with contextlib.suppress(Exception):
                await obj.close()
