"""Copilot answer service — the honest reuse layer.

Fans the PURE `retrieve()` seam over the cockpit + selfwiki KBs, merges + globally reindexes
the docs, then synthesizes ONE cited answer with the SAME `build_synthesis_kwargs()` the
grounded archetype uses. No WorkflowBuilder, no new SDK surface. Returns plain JSON so the Coach
Overlay never has to parse AG-UI SSE.

Verified against foundry-helpdesk:
- retrieve(query, user, domain, *, top=8) -> [{index, source, url, snippet}]  (app/services/retrieval.py)
- build_synthesis_kwargs(user_text, domain, docs, *, model) -> dict           (app/services/grounded.py)
- _async_credential(user)                                                      (app/services/grounded.py)
"""
from __future__ import annotations

import asyncio
import contextlib
import inspect
import time
from dataclasses import replace

from app.core.tenant import tenant_config
from app.domains import get_domain
from app.services.grounded import build_synthesis_kwargs
from app.services.retrieval import retrieve

# The two grounded KBs the copilot searches. cockpit-si-kb + selfwiki-si-kb are already indexed.
COPILOT_DOMAINS = ("cockpit", "selfwiki")

# Cap the docs fed to synthesis. The native KB retrieve returns the KB's full default set (~31 for
# cockpit) — passing all of them makes a huge prompt (slow + expensive). The top few (already in
# relevance order) are plenty for a 2–4 sentence answer, and keep the card's source list readable.
MAX_DOCS = 8


class _CopilotDomain:
    """Duck-typed domain for synthesis: build_synthesis_kwargs only reads `.instructions`."""

    def __init__(self, instructions: str) -> None:
        self.instructions = instructions


def _instructions_for(meeting_type: str) -> str:
    """Synthesis instructions with a tone adapted to the meeting type."""
    base = (
        "Você ajuda o apresentador a responder uma pergunta técnica feita numa call. "
        "Responda de forma curta (2–4 frases), em português, APENAS com base nos documentos "
        "fornecidos, citando cada afirmação pelo seu número entre colchetes, ex.: [1]. "
        "Se os documentos não contiverem a resposta, diga que não há informação suficiente."
    )
    tone = {
        "presentation": " Tom de negócio: foque benefícios e arquitetura de alto nível.",
        "technical": " Tom técnico: pode citar detalhes de implementação.",
        "sales": " Tom comercial: foque valor, segurança e escalabilidade.",
        "interview": " Tom conceitual: foque trade-offs e o porquê das decisões.",
    }.get(meeting_type, "")
    return base + tone


async def _synthesize(user_text: str, docs: list[dict], instructions: str, user) -> str:
    """Run the Foundry Responses synthesis AS THE USER (OBO) or app identity (dev), collecting
    the full (non-streamed) answer text.

    RULE #1: the non-streaming output field of `responses.create` is read via `getattr(resp,
    "output_text", "")`. Confirm this against the installed azure-ai-projects / openai SDK before
    relying on it in production — do NOT silently swap in a guessed attribute.
    """
    from azure.ai.projects.aio import AIProjectClient

    from app.services.grounded import _async_credential

    cfg = tenant_config()
    credential = _async_credential(user)
    proj = AIProjectClient(
        endpoint=cfg.foundry_project_endpoint, credential=credential, allow_preview=True
    )
    try:
        client = proj.get_openai_client()
        client = await client if inspect.isawaitable(client) else client
        kwargs = build_synthesis_kwargs(
            user_text, _CopilotDomain(instructions), docs, model=cfg.foundry_model
        )
        kwargs["stream"] = False
        resp = await client.responses.create(**kwargs)
        return getattr(resp, "output_text", "") or ""
    finally:
        for obj in (proj, credential):
            with contextlib.suppress(Exception):
                await obj.close()


async def answer_question(
    question: str, user=None, *, meeting_type: str = "presentation"
) -> dict:
    """Retrieve over both KBs → merge + globally reindex → synthesize one cited answer.

    Returns {answer, sources:[{index, kb, source, url, content}]}.
    """
    t0 = time.monotonic()

    async def _one(dom_id: str) -> list[dict]:
        # Force the FAST direct-search path: the domains have `kb_name`, which routes retrieve()
        # through the Foundry IQ *agentic* KB retrieve — an LLM-powered op that took ~27s. Dropping
        # kb_name makes retrieve() do a plain ACL-trimmed Azure AI Search over `search_index`
        # (~1s), returning the same {source,url,snippet}; WE synthesize once on top (no double-LLM).
        dom = replace(get_domain(dom_id), kb_name=None)
        rows = await retrieve(question, user, dom, top=MAX_DOCS)
        for r in rows:
            r["kb"] = dom_id
        return rows

    # Fan the two KB retrieves out CONCURRENTLY (was sequential → ~2× slower). Fail-soft per KB.
    results = await asyncio.gather(
        *[_one(d) for d in COPILOT_DOMAINS], return_exceptions=True
    )
    docs: list[dict] = []
    for r in results:
        if isinstance(r, list):
            docs.extend(r)
    t1 = time.monotonic()

    # Cap to the top MAX_DOCS (relevance order) BEFORE synthesis, then reindex 1..N so the [n]
    # citations map to `sources`.
    docs = docs[:MAX_DOCS]
    for i, d in enumerate(docs, start=1):
        d["index"] = i

    if not docs:
        return {
            "answer": "Não encontrei informações sobre isso nas KBs (cockpit/selfwiki).",
            "sources": [],
        }

    answer = await _synthesize(question, docs, _instructions_for(meeting_type), user)
    t2 = time.monotonic()
    print(
        f"[copilot] retrieve={t1 - t0:.1f}s synth={t2 - t1:.1f}s docs={len(docs)} q={question[:50]!r}"
    )
    sources = [
        {
            "index": d["index"],
            "kb": d.get("kb"),
            "source": d["source"],
            "url": d["url"],
            "content": (d.get("snippet") or "")[:800],
        }
        for d in docs
    ]
    return {"answer": answer, "sources": sources}
