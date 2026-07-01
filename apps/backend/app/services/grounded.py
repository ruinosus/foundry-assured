"""Grounded structured-citations bridge — Responses API (as the user, OBO) with structured citations.

Two paths, chosen by whether the domain needs per-user document ACL:

- **acl=False (Selfwiki, single-audience):** attach the KB as an inline Foundry IQ MCP tool
  (`knowledge_base_retrieve`). The agentic retrieve gives high-quality recall + native `url_citation`
  annotations. No ACL needed, so the (inert-on-the-agentic-path) header is irrelevant.

- **acl=True (Cockpit, per-user ACL):** the agentic `knowledge_base_retrieve` path does NOT honor the
  `x-ms-query-source-authorization` header on this service version (verified empirically; a known gap —
  azure-sdk-for-python#44454; the Microsoft ADLS-ACL tutorial only proves trimming on DIRECT search).
  So we can't let the model retrieve confidential content it isn't allowed to see. Instead we do
  **app-side retrieval + trim**: a DIRECT search over the index AS THE USER (the `x-ms-query-source-
  authorization` header DOES trim there, via the stamped `groups` field), which returns only the
  documents the user may read; then we synthesize the answer from ONLY those documents and emit their
  sources as citations. Fail-closed: the model never sees unauthorized content.

Both run the Responses API as the signed-in user (OBO for `https://ai.azure.com/.default` → no 403)
and re-emit AG-UI SSE (text deltas + a `sources` CUSTOM event) for the same CopilotChat.
Verified live in the STEP 0 findings (docs/superpowers/plans/2026-07-01-grounded-obo-citations-STEP0-findings.md).
"""

from __future__ import annotations

import inspect
import uuid
from collections.abc import AsyncGenerator
from dataclasses import dataclass

from app.core.settings import settings
from app.core.tenant import tenant_config

_SEARCH_SCOPE = "https://search.azure.com/.default"
_KB_API = "2026-05-01-preview"

# Appended for the MCP-tool (acl=False) path — the KB tool emits url_citation annotations when told to
# cite in this Microsoft-format marker.
CITATION_DIRECTIVE = (
    "Use SEMPRE a ferramenta da base de conhecimento para responder e cite as fontes. "
    "Toda afirmação fundamentada deve trazer anotações da ferramenta, renderizadas exatamente como "
    "【message_idx:search_idx†source_name】. Se a resposta não estiver na base, diga que não sabe."
)

# Prepended for the direct-search-synthesis (acl=True) path — the model answers ONLY from the
# authorized documents we retrieved and cites them by their [n] number.
SYNTHESIS_DIRECTIVE = (
    "Responda APENAS com base nos DOCUMENTOS fornecidos abaixo — nunca use conhecimento próprio. "
    "Cite a fonte de cada afirmação pelo seu número entre colchetes, ex.: [1]. Se os documentos não "
    "contiverem a resposta, diga que não sabe."
)


@dataclass(frozen=True)
class GroundedDomain:
    """Per-domain config for the grounded citations bridge (spec §3 domain_cfg)."""

    kb_name: str
    instructions: str
    acl: bool  # True → per-user ACL via direct-search+synthesize (cockpit); False → inline MCP tool (selfwiki)
    search_endpoint: str
    search_index: str | None = None  # required when acl=True (the index to direct-search)


def _server_url(domain: GroundedDomain) -> str:
    return f"{domain.search_endpoint.rstrip('/')}/knowledgebases/{domain.kb_name}/mcp?api-version={_KB_API}"


def build_responses_kwargs(
    user_text: str, domain: GroundedDomain, *, model: str, search_token: str
) -> dict:
    """The inline-MCP-tool `responses.create(**kwargs)` payload (acl=False path). Pure — no I/O."""
    tool: dict = {
        "type": "mcp",
        "server_label": "knowledge-base",
        "server_url": _server_url(domain),
        "allowed_tools": ["knowledge_base_retrieve"],
        "require_approval": "never",
        "authorization": search_token,  # primary auth to the Search MCP server (STEP 0)
    }
    return {
        "model": model,
        "input": user_text,
        "instructions": f"{domain.instructions}\n\n{CITATION_DIRECTIVE}",
        "tools": [tool],
        "stream": True,
    }


def build_synthesis_kwargs(
    user_text: str, domain: GroundedDomain, docs: list[dict], *, model: str
) -> dict:
    """The direct-search-synthesis `responses.create(**kwargs)` payload (acl=True path). Pure — no I/O.

    `docs` is the list of authorized documents (already ACL-trimmed by the direct search), each
    `{index, source, url, snippet}`. The snippets become the model's ONLY grounding context."""
    context = "\n\n".join(f"[{d['index']}] {d['source']}:\n{d.get('snippet', '')}" for d in docs)
    body = (
        f"{SYNTHESIS_DIRECTIVE}\n\n=== DOCUMENTOS ===\n{context}\n\n=== PERGUNTA ===\n{user_text}"
        if docs
        else f"{SYNTHESIS_DIRECTIVE}\n\n(Nenhum documento autorizado foi encontrado.)\n\n=== PERGUNTA ===\n{user_text}"
    )
    return {
        "model": model,
        "input": body,
        "instructions": domain.instructions,
        "stream": True,
    }


def _source_from_annotation(ann: object) -> dict | None:
    """`url_citation` annotation → {source, url}, or None for synthesis pseudo-cites / non-URL."""
    if ann is None:
        return None
    d = ann if isinstance(ann, dict) else (
        ann.model_dump() if hasattr(ann, "model_dump") else getattr(ann, "__dict__", {})
    )
    url = (d.get("url") or "").strip()
    if not url or url.startswith("mcp://"):
        return None
    return {"source": url.rsplit("/", 1)[-1], "url": url}


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


async def _direct_search_authorized(
    domain: GroundedDomain, query: str, primary_token: str, user_token: str | None, *, top: int = 8
) -> list[dict]:
    """DIRECT search over the index AS THE USER — the service trims by the stamped `groups` field
    (permissionFilterOption enabled), so the result contains ONLY documents the user may read.
    Returns authorized docs as [{index, source, url, snippet}]. This is where per-user ACL actually
    works (the agentic knowledge_base_retrieve path does not — see the module docstring)."""
    import httpx

    headers = {"Authorization": f"Bearer {primary_token}", "Content-Type": "application/json"}
    if user_token:
        headers["x-ms-query-source-authorization"] = user_token  # the ACL trim (real per-user)
    else:
        # Dev / auth-off: no caller identity. Elevated-read returns all docs so local dev isn't
        # fail-closed to public-only. Best-effort — if the identity lacks the elevated permission,
        # the query still runs (returns whatever the primary identity is entitled to).
        headers["x-ms-enable-elevated-read"] = "true"
    url = f"{domain.search_endpoint.rstrip('/')}/indexes/{domain.search_index}/docs/search?api-version={_KB_API}"
    body = {"search": query, "select": "snippet,blob_url", "top": top}
    async with httpx.AsyncClient(timeout=30) as http:
        resp = await http.post(url, headers=headers, json=body)
        resp.raise_for_status()
        rows = resp.json().get("value", [])
    docs: list[dict] = []
    seen: set[str] = set()
    for r in rows:
        blob = r.get("blob_url") or ""
        if not blob or blob in seen:
            continue
        seen.add(blob)
        docs.append({
            "index": len(docs) + 1,
            "source": blob.rsplit("/", 1)[-1],
            "url": blob,
            "snippet": r.get("snippet") or "",
        })
    return docs


async def stream_grounded_agui(body: dict, domain: GroundedDomain, user=None) -> AsyncGenerator[str]:
    """Stream a grounded answer (as the user) as AG-UI SSE: text deltas + a `sources` CUSTOM event.
    acl=False → inline MCP tool (native citations); acl=True → direct-search+synthesize (per-user ACL).

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

    user_text = _last_user_text(body.get("messages") or [])
    thread_id = body.get("threadId") or body.get("thread_id") or uuid.uuid4().hex
    run_id = body.get("runId") or body.get("run_id") or uuid.uuid4().hex

    enc = EventEncoder()
    yield enc.encode(RunStartedEvent(thread_id=thread_id, run_id=run_id))
    message_id = uuid.uuid4().hex
    yield enc.encode(TextMessageStartEvent(message_id=message_id, role="assistant"))

    cfg = tenant_config()
    credential = _async_credential(user)
    proj = AIProjectClient(
        endpoint=cfg.foundry_project_endpoint, credential=credential, allow_preview=True
    )
    sources: list[dict] = []
    seen: set[str] = set()
    # Two distinct identities: the model call runs AS THE USER (OBO → no 403 on inference), but SEARCH
    # access (the MCP tool `authorization` / the direct-search primary Authorization) uses the APP
    # identity, which holds Search Index Data Reader. The user's token can't be the search primary —
    # end users have no search RBAC; it's ONLY the per-user ACL header (x-ms-query-source-authorization).
    from azure.identity.aio import DefaultAzureCredential as _AppCredential

    app_credential = _AppCredential()
    try:
        app_search_token = (await app_credential.get_token(_SEARCH_SCOPE)).token  # app MI: Search Index Data Reader
        client = proj.get_openai_client()
        client = await client if inspect.isawaitable(client) else client

        if domain.acl:
            # Per-user ACL path: retrieve authorized docs via direct search (primary=app, ACL header=user),
            # then synthesize from ONLY those docs.
            user_search_token = (
                (await credential.get_token(_SEARCH_SCOPE)).token
                if (settings.auth_enabled and user is not None)
                else None
            )
            docs = await _direct_search_authorized(domain, user_text, app_search_token, user_search_token)
            sources = [{"index": d["index"], "source": d["source"], "url": d["url"]} for d in docs]
            kwargs = build_synthesis_kwargs(user_text, domain, docs, model=cfg.foundry_model)
        else:
            # Single-audience path: inline MCP tool (native url_citation annotations, collected below).
            kwargs = build_responses_kwargs(user_text, domain, model=cfg.foundry_model, search_token=app_search_token)

        stream = await client.responses.create(**kwargs)
        async for ev in stream:
            etype = getattr(ev, "type", "")
            if etype == "response.output_text.delta":
                delta = getattr(ev, "delta", "") or ""
                if delta:
                    yield enc.encode(TextMessageContentEvent(message_id=message_id, delta=delta))
            elif etype == "response.output_text.annotation.added":  # acl=False (MCP) citations
                s = _source_from_annotation(getattr(ev, "annotation", None))
                if s and s["url"] not in seen:
                    seen.add(s["url"])
                    sources.append({"index": len(sources) + 1, **s})
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        if sources:
            yield enc.encode(CustomEvent(name="sources", value=sources))
        yield enc.encode(RunFinishedEvent(thread_id=thread_id, run_id=run_id))
    except Exception as exc:  # surface to the UI as a clean run error (mirrors hosted.stream_agui)
        yield enc.encode(TextMessageEndEvent(message_id=message_id))
        yield enc.encode(RunErrorEvent(message=str(exc), code=type(exc).__name__))
    finally:
        import contextlib

        for obj in (proj, credential, app_credential):
            with contextlib.suppress(Exception):
                await obj.close()
