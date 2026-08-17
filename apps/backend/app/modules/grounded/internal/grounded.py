"""Grounded structured-citations bridge — ONE archetype over the `retrieve()` seam.

Four stations, one path (the old acl/MCP fork is gone — retrieval lives behind `app.modules.knowledge.internal.retrieval`):

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
import logging
import uuid
from collections.abc import AsyncGenerator

from app.modules.tenancy.public import tenant_config
from app.shared.settings import settings

# Prepended to the synthesis input — the model answers ONLY from the retrieved documents and cites them
# by their [n] number.
logger = logging.getLogger(__name__)


SYNTHESIS_DIRECTIVE = (
    "Responda APENAS com base nos DOCUMENTOS fornecidos abaixo — nunca use conhecimento próprio. "
    "Cite a fonte de cada afirmação pelo seu número entre colchetes, ex.: [1]. Se os documentos não "
    "contiverem a resposta, diga que não sabe."
)


# O pedido de idioma que viaja com a requisição. Curto e imperativo de propósito: cada
# instrução dinâmica anexada disputa contexto com as regras já compostas, então esta diz uma
# coisa só. A regra COMPLETA (incluindo não traduzir citação) mora no guardrail
# `response-language`, que já está no prompt composto — aqui só chega o valor.
def _language_directive(language: str | None) -> str:
    if not language:
        return ""
    return f"\n\nIdioma da resposta: {language}."


def build_synthesis_kwargs(
    user_text: str, domain, docs: list[dict], *, model: str, language: str | None = None
) -> dict:
    """The synthesis `responses.create(**kwargs)` payload. Pure — no I/O.

    `docs` is the list of retrieved (already ACL-trimmed + deduped) documents, each
    `{index, source, url, snippet}`. The snippets become the model's ONLY grounding context.
    `domain` is duck-typed: reads `.instructions`.

    `language` é a preferência de quem perguntou (de `Accept-Language`). Opcional: sem ela o
    agente segue o idioma da pergunta, que é o que o guardrail manda. O Foundry não tem campo
    de idioma para agentes de texto — procurado e não encontrado —, então isto é instrução."""
    context = "\n\n".join(f"[{d['index']}] {d['source']}:\n{d.get('snippet', '')}" for d in docs)
    body = (
        f"{SYNTHESIS_DIRECTIVE}\n\n=== DOCUMENTOS ===\n{context}\n\n=== PERGUNTA ===\n{user_text}"
        if docs
        else f"{SYNTHESIS_DIRECTIVE}\n\n(Nenhum documento autorizado foi encontrado.)\n\n=== PERGUNTA ===\n{user_text}"
    )
    return {
        "model": model,
        "input": body,
        "instructions": (getattr(domain, "instructions", "") or "") + _language_directive(language),
        "stream": True,
    }


def _async_credential(user):
    """Async credential AS THE SIGNED-IN USER (OBO), mirroring app.shared.auth.credential_for_request.
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


async def stream_grounded(body: dict, domain, user=None, language: str | None = None) -> AsyncGenerator[str]:
    """Stream a grounded answer (as the user) as AG-UI SSE: text deltas + a `sources` CUSTOM event.

    ONE archetype: retrieve via the `retrieve()` seam (per-user ACL / dedupe live there), then
    synthesize from ONLY those docs and emit their sources as citations.

    `user` is the signed-in User, CAPTURED IN THE ENDPOINT and passed in (the current_user() contextvar
    doesn't survive into this generator — see _async_credential). None → app identity (dev/no-auth).

    `language` chega do endpoint pelo mesmo motivo que `user`: é dado da requisição, e a
    requisição não sobrevive dentro do gerador do StreamingResponse."""
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

    from app.modules.hosted.public import last_user_text as _last_user_text
    from app.modules.knowledge.public import retrieve

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
        # Station 2 — retrieve: ONE line. The seam owns identity/ACL/dedupe (app.modules.knowledge.internal.retrieval).
        docs = await retrieve(user_text, user, domain)

        # SEGUNDA MÁXIMA: quem responde é o AGENTE PUBLICADO no Foundry, não um cliente anônimo
        # com o prompt colado na requisição. A diferença não é estética — antes desta linha o
        # recurso publicado era catálogo: aparecia no portal, tinha versão e histórico, e nunca
        # atendia ninguém. A versão que o portal mostra passa a ser a que responde.
        #
        # Fallback deliberado: se o agente não existir (projeto ainda sem ingest, nome renomeado),
        # cai no caminho anônimo com as instruções embutidas. Um domínio que para de responder
        # porque falta um recurso de catálogo seria pior que um que responde pelo caminho antigo —
        # e o aviso no log diz o que republicar.
        agent_name = getattr(domain, "id", None) or getattr(domain, "name", None)
        client = None
        if agent_name:
            try:
                client = proj.get_openai_client(agent_name=agent_name)
                client = await client if inspect.isawaitable(client) else client
            except Exception as exc:  # noqa: BLE001 — o domínio vale mais que a via preferida
                logger.warning(
                    "agente '%s' indisponível no Foundry (%s); usando o caminho anônimo. "
                    "Republique com `uv run python -m cli.provision_agents`.",
                    agent_name, exc,
                )
                client = None
        usando_agente = client is not None
        if client is None:
            client = proj.get_openai_client()
            client = await client if inspect.isawaitable(client) else client

        # Station 3 — synthesize: the retrieved docs are the ONLY grounding context (RULE #4).
        kwargs = build_synthesis_kwargs(
            user_text, domain, docs, model=cfg.foundry_model, language=language
        )
        if usando_agente:
            # As instruções JÁ estão no agente publicado — mandá-las de novo as duplicaria no
            # contexto e, pior, deixaria o prompt do repositório vencer o do serviço em silêncio
            # quando os dois divergissem. A versão publicada é a fonte quando o agente atende.
            kwargs.pop("instructions", None)
            # E o modelo precisa ser o DO AGENTE: o serviço recusa com "Model must match the
            # agent's model" quando um agente é especificado e o modelo diverge. Verificado.
            kwargs["model"] = cfg.foundry_model

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
